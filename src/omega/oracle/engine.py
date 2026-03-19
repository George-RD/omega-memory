"""OMEGA Oracle Engine -- Computed views over prediction memories.

Provides calibration curves, signal attribution, wallet rankings,
market bias maps, and regime playbooks by analyzing oracle_* memories
stored via omega_store. No dedicated tables; all intelligence is
computed on demand from the existing memories table.
"""

import logging
import threading
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from omega import json_compat as json

logger = logging.getLogger("omega.oracle.engine")

# Singleton (thread-safe)
_engine_instance: Optional["OracleEngine"] = None
_engine_lock = threading.Lock()

# Separate lock for resolve_prediction (cannot reuse db._lock — non-reentrant)
_resolve_lock = threading.Lock()


def get_oracle_engine() -> "OracleEngine":
    """Get or create the OracleEngine singleton (thread-safe)."""
    global _engine_instance
    if _engine_instance is None:
        with _engine_lock:
            if _engine_instance is None:
                _engine_instance = OracleEngine()
    return _engine_instance


class OracleEngine:
    """Computed views over Oracle prediction memories.

    All data lives in OMEGA\'s existing memories table as oracle_* event types.
    This engine queries those memories and computes analytical views on demand.
    """

    def _query_oracle_memories(
        self,
        event_type: str,
        limit: int = 500,
        days: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Query oracle memories of a specific type via direct SQL.

        Uses direct SQL on the memories table filtered by event_type column
        rather than semantic search, so it works without embeddings.

        Returns list of dicts with id, content, metadata, created_at.
        """
        from omega.bridge import _get_store

        db = _get_store()
        sql = "SELECT node_id, content, metadata, created_at FROM memories WHERE event_type = ?"
        params: list = [event_type]

        if days:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            sql += " AND created_at >= ?"
            params.append(cutoff)

        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        # Read-only query -- SQLite concurrent reads are safe in WAL mode.
        # We access _conn directly because the store has no public method for
        # event_type-filtered queries (only semantic search).
        rows = db._conn.execute(sql, params).fetchall()

        results = []
        for row in rows:
            meta = json.loads(row[2]) if row[2] else {}
            results.append({
                "id": row[0],
                "content": row[1],
                "metadata": meta,
                "created_at": row[3],
            })

        return results

    def _store_oracle(
        self,
        content: str,
        event_type: str,
        metadata: Dict[str, Any],
        entity_id: Optional[str] = None,
    ) -> str:
        """Store an oracle memory directly, bypassing embedding dedup.

        Oracle predictions are structurally similar but semantically distinct
        (different market_ids, probabilities, etc.). The embedding-based dedup
        in store_node (0.88 cosine threshold) would incorrectly merge them.
        We use skip_inference=True to bypass this while keeping canonical dedup.
        """
        from omega.bridge import _get_store
        from omega.types import TTLCategory

        metadata["event_type"] = event_type
        ttl = TTLCategory.for_event_type(event_type)

        db = _get_store()
        node_id = db.store(
            content=content,
            metadata=metadata,
            ttl_seconds=ttl,
            skip_inference=True,
            entity_id=entity_id,
        )
        return node_id

    def record_prediction(
        self, content: str, data: Dict[str, Any],
        market_type: str = "btc", entity_id: Optional[str] = None,
    ) -> str:
        """Store a prediction memory."""
        prob = data.get("our_probability")
        if prob is not None and not isinstance(prob, (int, float)):
            raise ValueError(f"our_probability must be numeric, got {type(prob).__name__}")
        return self._store_oracle(content, "oracle_prediction", {
            "oracle_data": data,
            "market_type": market_type,
            "market_id": data.get("market_id", ""),
            "resolved": False,
        }, entity_id=entity_id)

    def record_wallet_score(
        self, content: str, data: Dict[str, Any],
        market_type: str = "btc", entity_id: Optional[str] = None,
    ) -> str:
        """Store a wallet score memory."""
        return self._store_oracle(content, "oracle_wallet_score", {
            "oracle_data": data,
            "market_type": market_type,
            "address": data.get("address", ""),
        }, entity_id=entity_id)

    def record_regime_change(
        self, content: str, data: Dict[str, Any],
        entity_id: Optional[str] = None,
    ) -> str:
        """Store a regime change memory."""
        return self._store_oracle(content, "oracle_regime_change", {
            "oracle_data": data,
            "from_regime": data.get("from_regime", ""),
            "to_regime": data.get("to_regime", ""),
        }, entity_id=entity_id)

    def record_signal_snapshot(
        self, content: str, data: Dict[str, Any],
        market_type: str = "btc", entity_id: Optional[str] = None,
    ) -> str:
        """Store a signal snapshot memory."""
        return self._store_oracle(content, "oracle_signal_snapshot", {
            "oracle_data": data,
            "market_type": market_type,
        }, entity_id=entity_id)

    def resolve_prediction(self, market_id: str, outcome: str, resolution_price: Optional[float] = None) -> Dict[str, Any]:
        """Resolve a prediction by market_id. Updates the memory's metadata.

        Uses _resolve_lock to prevent TOCTOU races on concurrent resolution.
        """
        from omega.bridge import _get_store

        with _resolve_lock:
            db = _get_store()

            # Direct SQL lookup by market_id -- avoids scanning N predictions in Python
            try:
                row = db._conn.execute(
                    "SELECT node_id FROM memories "
                    "WHERE event_type = 'oracle_prediction' "
                    "AND json_extract(metadata, '$.market_id') = ? "
                    "AND json_extract(metadata, '$.resolved') = 0 "
                    "ORDER BY created_at DESC LIMIT 1",
                    (market_id,),
                ).fetchone()
            except Exception as e:
                logger.warning("Oracle SQL lookup failed for market_id=%s: %s", market_id, e)
                return {"success": False, "error": f"SQL lookup failed: {e}"}

            if not row:
                return {"success": False, "error": f"No unresolved prediction found for market_id={market_id}"}

            node_id = row[0]
            node = db.get_node(node_id)
            if not node:
                return {"success": False, "error": f"Memory node {node_id} not found"}

            meta = dict(node.metadata or {})
            meta["resolved"] = True
            meta["outcome"] = outcome
            meta["resolution_price"] = resolution_price
            meta["resolved_at"] = datetime.now(timezone.utc).isoformat()

            # Compute P&L using symmetric prediction market formula
            oracle_data = meta.get("oracle_data", {})
            if oracle_data:
                our_prob = oracle_data.get("our_probability", 0.5)
                market_price = oracle_data.get("market_price", 0.5)
                oracle_data["resolved"] = True
                oracle_data["outcome"] = outcome
                oracle_data["resolution_price"] = resolution_price
                # P&L based on position direction and market entry price
                predicted_yes = our_prob >= 0.5
                if predicted_yes:
                    # Bought YES at market_price
                    oracle_data["pnl"] = round((1 - market_price) if outcome == "yes" else -market_price, 4)
                else:
                    # Bought NO at (1 - market_price)
                    oracle_data["pnl"] = round(market_price if outcome == "no" else -(1 - market_price), 4)
                meta["oracle_data"] = oracle_data

            db.update_node(node_id, metadata=meta)

            return {
                "success": True,
                "market_id": market_id,
                "outcome": outcome,
                "memory_id": node_id,
                "pnl": oracle_data.get("pnl"),
            }
    def compute_calibration(
        self,
        market_type: Optional[str] = None,
        days: Optional[int] = None,
        n_bins: int = 10,
    ) -> Dict[str, Any]:
        """Compute calibration curve and Brier score from resolved predictions."""
        predictions = self._query_oracle_memories("oracle_prediction", limit=500, days=days)

        # Filter to resolved predictions
        resolved = []
        for p in predictions:
            meta = p.get("metadata", {})
            if not meta.get("resolved"):
                continue
            if market_type and meta.get("market_type") != market_type:
                continue
            oracle_data = meta.get("oracle_data", {})
            resolved.append({
                "our_probability": oracle_data.get("our_probability", 0.5),
                "outcome": meta.get("outcome", "no"),
                "market_type": meta.get("market_type", "btc"),
                "regime": oracle_data.get("regime"),
                "market_id": meta.get("market_id", ""),
            })

        if not resolved:
            return {
                "total_resolved": 0,
                "brier_score": None,
                "calibration_curve": [],
                "confidence_adjustments": {},
                "message": "No resolved predictions yet.",
            }

        # Brier score
        brier_sum = 0.0
        for p in resolved:
            predicted = p["our_probability"]
            actual = 1.0 if p["outcome"] == "yes" else 0.0
            brier_sum += (predicted - actual) ** 2
        brier_score = brier_sum / len(resolved)

        # Calibration curve
        bins = defaultdict(list)
        for p in resolved:
            prob = p["our_probability"]
            actual = 1.0 if p["outcome"] == "yes" else 0.0
            bin_idx = min(int(prob * n_bins), n_bins - 1)
            bins[bin_idx].append({"predicted": prob, "actual": actual})

        curve = []
        adjustments = {}
        for bin_idx in range(n_bins):
            bin_data = bins.get(bin_idx, [])
            if not bin_data:
                continue
            bin_center = (bin_idx + 0.5) / n_bins
            avg_predicted = sum(d["predicted"] for d in bin_data) / len(bin_data)
            avg_actual = sum(d["actual"] for d in bin_data) / len(bin_data)
            cal_error = avg_actual - avg_predicted
            curve.append({
                "bin_center": round(bin_center, 2),
                "avg_predicted": round(avg_predicted, 4),
                "avg_actual": round(avg_actual, 4),
                "count": len(bin_data),
                "calibration_error": round(cal_error, 4),
            })
            if len(bin_data) >= 5:
                adjustments[str(round(bin_center, 2))] = round(cal_error, 4)

        # Interpret Brier
        if brier_score < 0.10:
            interpretation = "excellent"
        elif brier_score < 0.20:
            interpretation = "good"
        elif brier_score < 0.25:
            interpretation = "acceptable"
        elif brier_score < 0.30:
            interpretation = "mediocre"
        else:
            interpretation = "poor"

        return {
            "total_resolved": len(resolved),
            "brier_score": round(brier_score, 4),
            "brier_interpretation": interpretation,
            "calibration_curve": curve,
            "confidence_adjustments": adjustments,
        }

    def compute_signal_attribution(
        self,
        market_type: Optional[str] = None,
        min_samples: int = 5,
    ) -> Dict[str, Any]:
        """Compute per-signal accuracy from resolved predictions.

        For each signal present in predictions, tracks how often predictions
        using that signal were correct. Segments by regime when possible.
        """
        predictions = self._query_oracle_memories("oracle_prediction", limit=500)

        resolved = []
        for p in predictions:
            meta = p.get("metadata", {})
            if not meta.get("resolved"):
                continue
            if market_type and meta.get("market_type") != market_type:
                continue
            oracle_data = meta.get("oracle_data", {})
            resolved.append({
                "outcome": meta.get("outcome", "no"),
                "our_probability": oracle_data.get("our_probability", 0.5),
                "signals_present": oracle_data.get("signals_present", []),
                "regime": oracle_data.get("regime"),
            })

        if not resolved:
            return {"signals": [], "message": "No resolved predictions with signal data."}

        # Aggregate per-signal accuracy
        signal_stats = defaultdict(lambda: {"correct": 0, "total": 0, "by_regime": defaultdict(lambda: {"correct": 0, "total": 0})})

        for p in resolved:
            outcome_actual = 1.0 if p["outcome"] == "yes" else 0.0
            our_prob = p["our_probability"]
            # Consider prediction "correct" if we were on the right side
            predicted_yes = our_prob >= 0.5
            actual_yes = outcome_actual >= 0.5
            correct = predicted_yes == actual_yes

            regime = p.get("regime", "unknown")

            for signal in p.get("signals_present", []):
                name = signal.get("name", "") if isinstance(signal, dict) else str(signal)
                if not name:
                    continue
                signal_stats[name]["total"] += 1
                signal_stats[name]["by_regime"][regime]["total"] += 1
                if correct:
                    signal_stats[name]["correct"] += 1
                    signal_stats[name]["by_regime"][regime]["correct"] += 1

        # Build ranked list
        signals = []
        for name, stats in signal_stats.items():
            if stats["total"] < min_samples:
                continue
            accuracy = stats["correct"] / stats["total"]
            regime_breakdown = {}
            for regime, rstats in stats["by_regime"].items():
                if rstats["total"] >= 3:
                    regime_breakdown[regime] = {
                        "accuracy": round(rstats["correct"] / rstats["total"], 4),
                        "count": rstats["total"],
                    }
            signals.append({
                "name": name,
                "accuracy": round(accuracy, 4),
                "total": stats["total"],
                "correct": stats["correct"],
                "by_regime": regime_breakdown,
            })

        signals.sort(key=lambda s: (-s["accuracy"], -s["total"]))

        return {
            "total_resolved": len(resolved),
            "signals": signals,
        }

    def get_wallet_rankings(
        self,
        market_type: Optional[str] = None,
        min_trades: int = 5,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Rank wallets by accuracy from stored wallet scores."""
        wallet_memories = self._query_oracle_memories("oracle_wallet_score", limit=500)

        # Deduplicate by address (keep latest)
        wallets_by_addr = {}
        for w in wallet_memories:
            meta = w.get("metadata", {})
            if market_type and meta.get("market_type") != market_type:
                continue
            oracle_data = meta.get("oracle_data", {})
            addr = oracle_data.get("address", meta.get("address", ""))
            if not addr:
                continue
            trade_count = oracle_data.get("trade_count", 0)
            if trade_count < min_trades:
                continue
            # Keep latest by checking if we already have this address
            if addr not in wallets_by_addr:
                wallets_by_addr[addr] = oracle_data
            else:
                # Compare trade counts, keep higher
                if trade_count > wallets_by_addr[addr].get("trade_count", 0):
                    wallets_by_addr[addr] = oracle_data

        # Rank by Brier score (lower is better) then by trade count
        ranked = sorted(
            wallets_by_addr.values(),
            key=lambda w: (w.get("brier_score", 1.0), -w.get("trade_count", 0)),
        )[:limit]

        follow = [w for w in ranked if w.get("is_informed")]
        fade = [w for w in ranked if not w.get("is_informed") and w.get("brier_score", 0) > 0.35]

        return {
            "total_wallets": len(wallets_by_addr),
            "top_wallets": ranked,
            "follow_recommendations": [w.get("address") for w in follow[:5]],
            "fade_recommendations": [w.get("address") for w in fade[:3]],
        }

    def get_market_bias(
        self,
        market_type: Optional[str] = None,
        subtype: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Catalog systematic mispricings from resolved predictions.

        Groups predictions by market subtype and regime, identifies
        patterns where our estimate consistently differs from market price.
        """
        predictions = self._query_oracle_memories("oracle_prediction", limit=500)

        resolved = []
        for p in predictions:
            meta = p.get("metadata", {})
            if not meta.get("resolved"):
                continue
            if market_type and meta.get("market_type") != market_type:
                continue
            oracle_data = meta.get("oracle_data", {})
            resolved.append({
                "market_type": meta.get("market_type", "btc"),
                "regime": oracle_data.get("regime", "unknown"),
                "our_probability": oracle_data.get("our_probability", 0.5),
                "market_price": oracle_data.get("market_price", 0.5),
                "outcome": meta.get("outcome", "no"),
                "edge": oracle_data.get("edge", 0),
            })

        if not resolved:
            return {"biases": [], "message": "No resolved predictions for bias analysis."}

        # Group by regime
        by_regime = defaultdict(list)
        for p in resolved:
            by_regime[p["regime"]].append(p)

        biases = []
        for regime, preds in by_regime.items():
            if len(preds) < 3:
                continue
            avg_edge = sum(p["edge"] for p in preds) / len(preds)
            avg_market = sum(p["market_price"] for p in preds) / len(preds)
            # Track whether market was systematically high or low
            market_overpriced = sum(
                1 for p in preds
                if (p["outcome"] == "no" and p["market_price"] > 0.5)
                or (p["outcome"] == "yes" and p["market_price"] < 0.5)
            )
            market_accuracy = 1 - (market_overpriced / len(preds))

            biases.append({
                "regime": regime,
                "count": len(preds),
                "avg_edge": round(avg_edge, 4),
                "avg_market_price": round(avg_market, 4),
                "market_accuracy": round(market_accuracy, 4),
                "direction": "overpriced" if avg_edge > 0 else "underpriced",
            })

        return {
            "total_resolved": len(resolved),
            "biases": biases,
        }

    def get_regime_playbook(
        self,
        current_regime: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build optimal strategy per regime from historical performance.

        Returns what signal weights, Kelly fraction, and prompt strategy
        worked best in each regime.
        """
        predictions = self._query_oracle_memories("oracle_prediction", limit=500)
        regime_changes = self._query_oracle_memories("oracle_regime_change", limit=100)

        # Group resolved predictions by regime
        by_regime = defaultdict(list)
        for p in predictions:
            meta = p.get("metadata", {})
            if not meta.get("resolved"):
                continue
            oracle_data = meta.get("oracle_data", {})
            regime = oracle_data.get("regime", "unknown")
            by_regime[regime].append({
                "our_probability": oracle_data.get("our_probability", 0.5),
                "outcome": meta.get("outcome", "no"),
                "edge": oracle_data.get("edge", 0),
                "ensemble_strategies": oracle_data.get("ensemble_strategies", {}),
                "signals_present": oracle_data.get("signals_present", []),
                "pnl": oracle_data.get("pnl"),
            })

        playbooks = {}
        for regime, preds in by_regime.items():
            if len(preds) < 3:
                continue

            # Brier score for this regime
            brier_sum = sum(
                (p["our_probability"] - (1.0 if p["outcome"] == "yes" else 0.0)) ** 2
                for p in preds
            )
            brier = brier_sum / len(preds)

            # Best strategy per regime
            strategy_scores = defaultdict(list)
            for p in preds:
                actual = 1.0 if p["outcome"] == "yes" else 0.0
                for strat_name, strat_data in p.get("ensemble_strategies", {}).items():
                    # Accept both dict with probability_yes key and bare float
                    if isinstance(strat_data, dict):
                        prob = strat_data.get("probability_yes")
                    elif isinstance(strat_data, (int, float)):
                        prob = strat_data
                    else:
                        prob = None
                    if prob is not None:
                        strategy_scores[strat_name].append((prob - actual) ** 2)

            best_strategies = {}
            for strat, scores in strategy_scores.items():
                best_strategies[strat] = round(sum(scores) / len(scores), 4)

            # Best signals
            signal_accuracy = defaultdict(lambda: {"correct": 0, "total": 0})
            for p in preds:
                correct = (p["our_probability"] >= 0.5) == (p["outcome"] == "yes")
                for sig in p.get("signals_present", []):
                    name = sig.get("name", "") if isinstance(sig, dict) else str(sig)
                    if name:
                        signal_accuracy[name]["total"] += 1
                        if correct:
                            signal_accuracy[name]["correct"] += 1

            top_signals = sorted(
                [
                    {"name": name, "accuracy": round(s["correct"] / s["total"], 4), "count": s["total"]}
                    for name, s in signal_accuracy.items()
                    if s["total"] >= 3
                ],
                key=lambda x: -x["accuracy"],
            )[:5]

            # Recommended Kelly fraction based on Brier
            if brier < 0.15:
                kelly_rec = 0.25
            elif brier < 0.25:
                kelly_rec = 0.15
            else:
                kelly_rec = 0.10

            total_pnl = sum(p.get("pnl") or 0 for p in preds)

            playbooks[regime] = {
                "count": len(preds),
                "brier_score": round(brier, 4),
                "total_pnl": round(total_pnl, 4),
                "best_strategies": best_strategies,
                "top_signals": top_signals,
                "recommended_kelly": kelly_rec,
            }

        # Add regime transition history
        transitions = []
        for rc in regime_changes:
            meta = rc.get("metadata", {})
            oracle_data = meta.get("oracle_data", {})
            transitions.append({
                "from": oracle_data.get("from_regime") or meta.get("from_regime"),
                "to": oracle_data.get("to_regime") or meta.get("to_regime"),
                "confidence": oracle_data.get("confidence"),
            })

        result = {
            "playbooks": playbooks,
            "regime_transitions": transitions[:10],
        }

        if current_regime and current_regime in playbooks:
            result["current_playbook"] = playbooks[current_regime]
            result["current_regime"] = current_regime

        return result

    def get_briefing(self, market_type: str = "btc") -> Dict[str, Any]:
        """Composite briefing combining all analytical views.

        Designed for injection into the probability estimator's context.
        """
        calibration = self.compute_calibration(market_type=market_type)
        signals = self.compute_signal_attribution(market_type=market_type)
        wallets = self.get_wallet_rankings(market_type=market_type)
        bias = self.get_market_bias(market_type=market_type)
        playbook = self.get_regime_playbook()

        # Build concise briefing text
        lines = []
        lines.append(f"=== Oracle Briefing ({market_type.upper()}) ===")

        # Calibration summary
        if calibration.get("brier_score") is not None:
            lines.append(f"\nCalibration: Brier={calibration['brier_score']:.4f} "
                        f"({calibration['brier_interpretation']}) "
                        f"from {calibration['total_resolved']} resolved predictions")
            for point in calibration.get("calibration_curve", []):
                error = point["calibration_error"]
                if abs(error) >= 0.03:
                    direction = "overconfident" if error < 0 else "underconfident"
                    lines.append(f"  At {point['avg_predicted']:.0%}: "
                                f"{direction} by {abs(error):.1%} (n={point['count']})")

        # Signal attribution
        top_signals = signals.get("signals", [])[:5]
        if top_signals:
            lines.append("\nTop signals by accuracy:")
            for s in top_signals:
                lines.append(f"  {s['name']}: {s['accuracy']:.0%} ({s['total']} predictions)")

        # Wallet insights
        follow = wallets.get("follow_recommendations", [])
        if follow:
            lines.append(f"\nInformed wallets to follow: {len(follow)}")

        # Bias patterns
        for b in bias.get("biases", []):
            if abs(b["avg_edge"]) > 0.03:
                lines.append(f"\nBias in {b['regime']} regime: "
                            f"markets tend to be {b['direction']} by {abs(b['avg_edge']):.1%}")

        # Current playbook
        if playbook.get("current_playbook"):
            pb = playbook["current_playbook"]
            lines.append(f"\nCurrent regime playbook (Brier={pb['brier_score']:.4f}):")
            lines.append(f"  Recommended Kelly: {pb['recommended_kelly']}")
            for s in pb.get("top_signals", [])[:3]:
                lines.append(f"  Best signal: {s['name']} ({s['accuracy']:.0%})")

        briefing_text = "\n".join(lines)

        return {
            "briefing_text": briefing_text,
            "calibration": calibration,
            "signals": signals,
            "wallets": wallets,
            "bias": bias,
            "playbook": playbook,
        }

    def get_status(self) -> Dict[str, Any]:
        """Dashboard: prediction count, resolved count, current Brier, etc."""
        predictions = self._query_oracle_memories("oracle_prediction", limit=500)
        wallet_scores = self._query_oracle_memories("oracle_wallet_score", limit=100)
        regime_changes = self._query_oracle_memories("oracle_regime_change", limit=10)
        signal_snapshots = self._query_oracle_memories("oracle_signal_snapshot", limit=10)

        total = len(predictions)
        resolved = sum(1 for p in predictions if p.get("metadata", {}).get("resolved"))

        # Current Brier
        cal = self.compute_calibration()
        brier = cal.get("brier_score")

        # Active regime (from latest regime change)
        active_regime = None
        if regime_changes:
            latest_rc = regime_changes[0]
            meta = latest_rc.get("metadata", {})
            oracle_data = meta.get("oracle_data", {})
            active_regime = oracle_data.get("to_regime") or meta.get("to_regime")

        return {
            "prediction_count": total,
            "resolved_count": resolved,
            "unresolved_count": total - resolved,
            "brier_score": brier,
            "brier_interpretation": cal.get("brier_interpretation"),
            "wallet_scores_count": len(wallet_scores),
            "regime_changes_count": len(regime_changes),
            "signal_snapshots_count": len(signal_snapshots),
            "active_regime": active_regime,
        }
