# Berman-Inspired Systems Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement 5 systems inspired by Matthew Berman's OpenClaw patterns across OMEGA, polymarket-omega, and Conductor.

**Architecture:** Additive changes only — no breaking changes. Each system is independently deployable. OMEGA gets notification batching (coord DB v11) + LLM usage tracking + council tool. polymarket-omega gets a signal scoring rubric. Conductor gets cron job infrastructure.

**Tech Stack:** Python 3.11+ (OMEGA, polymarket-omega), Python 3.12+ (Conductor), Next.js/TypeScript (OMEGA admin dashboard), SQLite WAL mode throughout.

---

## Task 1: Notification Batching in OMEGA Coordination

**Files:**
- Modify: `/Users/singularityjason/Projects/omega/src/omega/coordination.py`
- Modify: `/Users/singularityjason/Projects/omega/src/omega/server/coord_handlers.py`
- Modify: `/Users/singularityjason/Projects/omega/src/omega/server/coord_schemas.py`
- Test: `/Users/singularityjason/Projects/omega/tests/test_coordination.py`

### Step 1: Write the failing test for schema migration

```python
# In tests/test_coordination.py — add at end of file

def test_coord_messages_has_priority_columns(tmp_path):
    """v11 migration adds priority, batch_id, delivered_at to coord_messages."""
    from omega.coordination import CoordinationManager

    mgr = CoordinationManager(db_path=str(tmp_path / "coord.db"))
    # Check columns exist
    with mgr._lock:
        cols = [
            row[1]
            for row in mgr._conn.execute("PRAGMA table_info(coord_messages)").fetchall()
        ]
    assert "priority" in cols
    assert "batch_id" in cols
    assert "delivered_at" in cols
    mgr.close()
```

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_coordination.py::test_coord_messages_has_priority_columns -xvs`
Expected: FAIL — columns don't exist yet.

### Step 2: Add v11 schema migration

In `/Users/singularityjason/Projects/omega/src/omega/coordination.py`:

1. Change `COORD_SCHEMA_VERSION = 10` to `COORD_SCHEMA_VERSION = 11` (line 44)

2. Add columns to `coord_messages` CREATE TABLE (after line 404, before the closing paren):
```python
    priority TEXT DEFAULT 'medium',
    batch_id TEXT,
    delivered_at TEXT
```

3. Add index after the existing `idx_coord_messages_created` index:
```python
c.execute("""CREATE INDEX IF NOT EXISTS idx_coord_messages_pending
             ON coord_messages(priority, delivered_at)
             WHERE delivered_at IS NULL""")
```

4. Add migration block inside `_migrate_schema()` (after the `if from_version < 10:` block):
```python
if from_version < 11:
    for col_sql in (
        "ALTER TABLE coord_messages ADD COLUMN priority TEXT DEFAULT 'medium'",
        "ALTER TABLE coord_messages ADD COLUMN batch_id TEXT",
        "ALTER TABLE coord_messages ADD COLUMN delivered_at TEXT",
    ):
        try:
            c.execute(col_sql)
        except sqlite3.OperationalError:
            pass
    try:
        c.execute(
            """CREATE INDEX IF NOT EXISTS idx_coord_messages_pending
               ON coord_messages(priority, delivered_at)
               WHERE delivered_at IS NULL"""
        )
    except sqlite3.OperationalError:
        pass
    _retry_on_locked(c.commit)
```

### Step 3: Run test to verify migration passes

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_coordination.py::test_coord_messages_has_priority_columns -xvs`
Expected: PASS

### Step 4: Write tests for send_message with priority

```python
def test_send_message_critical_delivered_immediately(tmp_path):
    """Critical messages set delivered_at immediately."""
    from omega.coordination import CoordinationManager

    mgr = CoordinationManager(db_path=str(tmp_path / "coord.db"))
    mgr.register_session("sender", pid=1, project="test")
    mgr.register_session("receiver", pid=2, project="test")

    result = mgr.send_message(
        from_session="sender",
        subject="urgent",
        msg_type="inform",
        to_session="receiver",
        priority="critical",
    )
    assert result["success"]

    # Check delivered_at is set
    with mgr._lock:
        row = mgr._conn.execute(
            "SELECT priority, delivered_at FROM coord_messages WHERE id = ?",
            (result["message_id"],),
        ).fetchone()
    assert row[0] == "critical"
    assert row[1] is not None  # delivered_at is set
    mgr.close()


def test_send_message_medium_not_delivered(tmp_path):
    """Medium priority messages have delivered_at = NULL (pending batch)."""
    from omega.coordination import CoordinationManager

    mgr = CoordinationManager(db_path=str(tmp_path / "coord.db"))
    mgr.register_session("sender", pid=1, project="test")
    mgr.register_session("receiver", pid=2, project="test")

    result = mgr.send_message(
        from_session="sender",
        subject="routine update",
        msg_type="inform",
        to_session="receiver",
        priority="medium",
    )
    assert result["success"]

    with mgr._lock:
        row = mgr._conn.execute(
            "SELECT priority, delivered_at FROM coord_messages WHERE id = ?",
            (result["message_id"],),
        ).fetchone()
    assert row[0] == "medium"
    assert row[1] is None  # not yet delivered
    mgr.close()


def test_send_message_default_priority_is_medium(tmp_path):
    """Default priority (no param) = medium for backwards compat."""
    from omega.coordination import CoordinationManager

    mgr = CoordinationManager(db_path=str(tmp_path / "coord.db"))
    mgr.register_session("sender", pid=1, project="test")
    mgr.register_session("receiver", pid=2, project="test")

    result = mgr.send_message(
        from_session="sender",
        subject="no priority specified",
        msg_type="inform",
        to_session="receiver",
    )
    assert result["success"]

    with mgr._lock:
        row = mgr._conn.execute(
            "SELECT priority FROM coord_messages WHERE id = ?",
            (result["message_id"],),
        ).fetchone()
    assert row[0] == "medium"
    mgr.close()
```

### Step 5: Run tests to verify they fail

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_coordination.py -k "priority" -xvs`
Expected: FAIL — send_message doesn't accept priority yet.

### Step 6: Modify send_message in coordination.py

Find the `send_message()` method in `coordination.py`. Add `priority: str = "medium"` parameter. In the INSERT statement, add the priority column and set `delivered_at`:

```python
def send_message(
    self,
    from_session: str,
    subject: str,
    msg_type: str = "inform",
    to_session: Optional[str] = None,
    body: Optional[str] = None,
    context_id: Optional[str] = None,
    ref_task_id: Optional[int] = None,
    ttl_minutes: Optional[int] = None,
    priority: str = "medium",  # NEW
) -> Dict[str, Any]:
```

In the INSERT SQL, add `priority, delivered_at` columns. Set `delivered_at`:
```python
now = datetime.now(timezone.utc).isoformat()
delivered_at = now if priority == "critical" else None
```

### Step 7: Run priority tests to verify they pass

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_coordination.py -k "priority" -xvs`
Expected: PASS

### Step 8: Write test for flush_notification_batch

```python
def test_flush_notification_batch(tmp_path):
    """flush_notification_batch delivers pending high-priority messages."""
    from omega.coordination import CoordinationManager
    from datetime import datetime, timezone, timedelta

    mgr = CoordinationManager(db_path=str(tmp_path / "coord.db"))
    mgr.register_session("sender", pid=1, project="test")
    mgr.register_session("receiver", pid=2, project="test")

    # Send a high-priority message
    result = mgr.send_message(
        from_session="sender",
        subject="high prio update",
        msg_type="inform",
        to_session="receiver",
        priority="high",
    )
    msg_id = result["message_id"]

    # Backdate created_at to 2 hours ago so it's past the 1h cutoff
    two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    with mgr._lock:
        mgr._conn.execute(
            "UPDATE coord_messages SET created_at = ? WHERE id = ?",
            (two_hours_ago, msg_id),
        )
        mgr._conn.commit()

    # Flush
    flushed = mgr.flush_notification_batch()
    assert flushed > 0

    # Verify delivered_at is now set
    with mgr._lock:
        row = mgr._conn.execute(
            "SELECT delivered_at, batch_id FROM coord_messages WHERE id = ?",
            (msg_id,),
        ).fetchone()
    assert row[0] is not None
    assert row[1] is not None  # batch_id assigned
    mgr.close()
```

### Step 9: Implement flush_notification_batch

Add to `CoordinationManager` in `coordination.py`:

```python
def flush_notification_batch(self) -> int:
    """Flush pending batched notifications. Returns count of messages delivered."""
    now = datetime.now(timezone.utc)
    batch_id = uuid.uuid4().hex[:8]
    total_flushed = 0

    with self._lock:
        for priority, cutoff_hours in [("high", 1), ("medium", 3)]:
            cutoff = (now - timedelta(hours=cutoff_hours)).isoformat()
            rows = self._conn.execute(
                """SELECT id, to_session, project, from_session, subject, msg_type
                   FROM coord_messages
                   WHERE delivered_at IS NULL
                     AND priority = ?
                     AND created_at < ?
                     AND (expires_at IS NULL OR expires_at > ?)""",
                (priority, cutoff, now.isoformat()),
            ).fetchall()

            if not rows:
                continue

            msg_ids = [r[0] for r in rows]
            self._conn.execute(
                f"""UPDATE coord_messages
                    SET delivered_at = ?, batch_id = ?
                    WHERE id IN ({','.join('?' * len(msg_ids))})""",
                [now.isoformat(), batch_id] + msg_ids,
            )
            _retry_on_locked(self._conn.commit)
            total_flushed += len(rows)

    return total_flushed
```

### Step 10: Run flush test

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_coordination.py::test_flush_notification_batch -xvs`
Expected: PASS

### Step 11: Update coord_handlers.py to pass priority

In `handle_send_message()` (coord_handlers.py ~line 970), extract priority from arguments and pass to `mgr.send_message()`:

```python
priority = arguments.get("priority", "medium")
if priority not in ("critical", "high", "medium"):
    priority = "medium"
```

Pass it: `result = mgr.send_message(..., priority=priority)`

Conditionally skip `notify_session()` for non-critical:
```python
if result.get("success") and priority == "critical":
    # existing notify_session() block
```

### Step 12: Update coord_schemas.py

In the `omega_send_message` schema (line ~310), add priority property:

```python
"priority": {
    "type": "string",
    "description": "Notification priority: critical (immediate), high (hourly batch), medium (3-hour batch)",
    "enum": ["critical", "high", "medium"],
    "default": "medium",
},
```

### Step 13: Run full coordination test suite

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_coordination.py -x --timeout=60`
Expected: All PASS

### Step 14: Commit

```bash
cd ~/Projects/omega
git add src/omega/coordination.py src/omega/server/coord_handlers.py src/omega/server/coord_schemas.py tests/test_coordination.py
git commit -m "feat(coordination): add notification batching with 3-tier priority

Messages now support priority levels: critical (immediate delivery),
high (hourly batch), and medium (3-hour batch). Adds flush_notification_batch()
for maintenance cycle integration. Schema v11."
```

---

## Task 2: Signal Scoring Rubric for polymarket-omega

**Files:**
- Create: `/Users/singularityjason/Projects/polymarket-omega/config/signal_rubric.md`
- Create: `/Users/singularityjason/Projects/polymarket-omega/lib/signal_scorer.py`
- Modify: `/Users/singularityjason/Projects/polymarket-omega/agents/probability_estimator.py`
- Modify: `/Users/singularityjason/Projects/polymarket-omega/agents/calibrator.py`
- Test: `/Users/singularityjason/Projects/polymarket-omega/tests/test_signal_scorer.py`

### Step 1: Create the rubric markdown file

Create `/Users/singularityjason/Projects/polymarket-omega/config/signal_rubric.md`:

```markdown
# Signal Scoring Rubric

Score each incoming signal on 5 dimensions. Weighted sum determines the bucket.

## Dimensions

| Dimension | Weight | 0-20 (Low) | 40-60 (Medium) | 80-100 (High) |
|-----------|--------|------------|-----------------|----------------|
| Source Credibility | 0.25 | Unknown source, no track record | Established but limited history | Government/institutional data, verified accuracy |
| Signal Magnitude | 0.20 | Within 0.5 sigma of baseline | 1-2 sigma deviation | 3+ sigma deviation |
| Time Sensitivity | 0.20 | Beyond 3 half-lives old | 1-2 half-lives old | Within 1 half-life, fresh |
| Corroboration | 0.20 | Single source, no confirmation | 1-2 independent confirmations | 3+ independent sources agree |
| Novelty | 0.15 | Restating known information | Incremental update to known facts | First report of genuinely new data |

## Score Buckets

| Bucket | Range | Action |
|--------|-------|--------|
| exceptional | 80-100 | Boost ensemble weight 1.5x. Alert user immediately. |
| high | 60-79 | Standard ensemble weight. Include in daily digest with emphasis. |
| medium | 40-59 | Standard processing. |
| low | 20-39 | Downweight ensemble 0.5x. Log only. |
| noise | 0-19 | Skip from ensemble entirely. Log exclusion reason. |

## Source Credibility Baselines

| Source Key | Default Score | Notes |
|------------|--------------|-------|
| sosovalue_etf | 85 | Primary ETF flow source, verified |
| coinglass_etf | 80 | Paid backup, reliable |
| coinmetrics | 80 | Academic-grade on-chain |
| bgeometrics | 70 | Free tier, rate-limited |
| mempool_space | 75 | Open-source, live |
| bls_macro | 90 | US government data |
| sharpe_mindshare | 55 | Newer, validate against outcomes |
| kaito_yaps | 50 | Social signal, inherently noisy |
| polymarket_vpin | 65 | Derived, depends on liquidity |
| deribit_options | 75 | Market-implied, liquid |
| fear_greed | 45 | Sentiment index, contrarian use |
```

### Step 2: Write the failing test for SignalScorer

Create `/Users/singularityjason/Projects/polymarket-omega/tests/test_signal_scorer.py`:

```python
"""Tests for signal scoring rubric system."""
import json
import os
import pytest
from pathlib import Path


@pytest.fixture
def rubric_path():
    return str(Path(__file__).parent.parent / "config" / "signal_rubric.md")


@pytest.fixture
def sample_signals():
    return [
        {
            "source_key": "sosovalue_etf",
            "name": "ETF Net Flow",
            "value": 500_000_000,
            "baseline_value": 100_000_000,
            "baseline_std": 80_000_000,
            "timestamp": "2026-02-26T10:00:00Z",
            "half_life_hours": 48,
            "corroborating_sources": ["coinglass_etf", "coinmetrics"],
            "is_novel": True,
        },
        {
            "source_key": "kaito_yaps",
            "name": "BTC Social Mindshare",
            "value": 12.5,
            "baseline_value": 10.0,
            "baseline_std": 3.0,
            "timestamp": "2026-02-25T08:00:00Z",
            "half_life_hours": 24,
            "corroborating_sources": [],
            "is_novel": False,
        },
    ]


def test_score_signal_returns_required_fields(rubric_path, sample_signals):
    from lib.signal_scorer import SignalScorer

    scorer = SignalScorer(rubric_path=rubric_path)
    result = scorer.score_signal(sample_signals[0])
    assert "score" in result
    assert "bucket" in result
    assert "breakdown" in result
    assert "action" in result
    assert 0 <= result["score"] <= 100


def test_high_quality_signal_scores_high(rubric_path, sample_signals):
    from lib.signal_scorer import SignalScorer

    scorer = SignalScorer(rubric_path=rubric_path)
    result = scorer.score_signal(sample_signals[0])
    # ETF flow: high credibility (85), 5-sigma deviation, fresh, 2 corroborations, novel
    assert result["score"] >= 70
    assert result["bucket"] in ("exceptional", "high")


def test_noisy_signal_scores_low(rubric_path, sample_signals):
    from lib.signal_scorer import SignalScorer

    scorer = SignalScorer(rubric_path=rubric_path)
    result = scorer.score_signal(sample_signals[1])
    # Kaito: low credibility (50), <1 sigma, 26h old (>1 half-life), no corroboration, not novel
    assert result["score"] < 50
    assert result["bucket"] in ("low", "medium")


def test_score_batch_returns_sorted(rubric_path, sample_signals):
    from lib.signal_scorer import SignalScorer

    scorer = SignalScorer(rubric_path=rubric_path)
    results = scorer.score_batch(sample_signals)
    assert len(results) == 2
    assert results[0]["score"] >= results[1]["score"]


def test_rubric_parsing(rubric_path):
    from lib.signal_scorer import SignalScorer

    scorer = SignalScorer(rubric_path=rubric_path)
    assert "sosovalue_etf" in scorer.source_baselines
    assert scorer.source_baselines["bls_macro"] == 90
    assert len(scorer.dimension_weights) == 5
    assert abs(sum(scorer.dimension_weights.values()) - 1.0) < 0.01
```

Run: `cd ~/Projects/polymarket-omega && python3.11 -m pytest tests/test_signal_scorer.py -xvs`
Expected: FAIL — `lib.signal_scorer` doesn't exist.

### Step 3: Implement SignalScorer

Create `/Users/singularityjason/Projects/polymarket-omega/lib/signal_scorer.py`:

```python
"""Signal scoring rubric system.

Scores incoming signals on 5 dimensions using an editable markdown rubric.
Rubric lives at config/signal_rubric.md and can be tuned without code changes.
"""
import re
from datetime import datetime, timezone
from pathlib import Path


# Bucket definitions: (min_score, name, action)
BUCKETS = [
    (80, "exceptional", "Boost ensemble weight 1.5x. Alert user immediately."),
    (60, "high", "Standard ensemble weight. Include in daily digest with emphasis."),
    (40, "medium", "Standard processing."),
    (20, "low", "Downweight ensemble 0.5x. Log only."),
    (0, "noise", "Skip from ensemble entirely. Log exclusion reason."),
]


class SignalScorer:
    def __init__(self, rubric_path: str = "config/signal_rubric.md"):
        self.rubric_path = rubric_path
        self.dimension_weights: dict[str, float] = {}
        self.source_baselines: dict[str, int] = {}
        self._parse_rubric()

    def _parse_rubric(self) -> None:
        """Parse the markdown rubric for weights and baselines."""
        text = Path(self.rubric_path).read_text()

        # Parse dimension weights from the Dimensions table
        dim_pattern = r"\|\s*([\w\s]+?)\s*\|\s*([\d.]+)\s*\|"
        in_dimensions = False
        for line in text.split("\n"):
            if "## Dimensions" in line:
                in_dimensions = True
                continue
            if in_dimensions and line.startswith("## "):
                break
            if in_dimensions:
                m = re.match(dim_pattern, line)
                if m:
                    name = m.group(1).strip().lower().replace(" ", "_")
                    weight = float(m.group(2))
                    self.dimension_weights[name] = weight

        # Parse source credibility baselines
        in_baselines = False
        for line in text.split("\n"):
            if "## Source Credibility Baselines" in line:
                in_baselines = True
                continue
            if in_baselines and line.startswith("## "):
                break
            if in_baselines:
                m = re.match(r"\|\s*(\w+)\s*\|\s*(\d+)\s*\|", line)
                if m:
                    self.source_baselines[m.group(1)] = int(m.group(2))

    def score_signal(self, signal: dict) -> dict:
        """Score a single signal against the rubric dimensions."""
        breakdown = {}

        # 1. Source Credibility (from baselines table)
        source_key = signal.get("source_key", "")
        credibility = self.source_baselines.get(source_key, 40)
        breakdown["source_credibility"] = credibility

        # 2. Signal Magnitude (z-score based)
        value = signal.get("value", 0)
        baseline = signal.get("baseline_value", 0)
        std = signal.get("baseline_std", 1)
        if std > 0:
            z = abs(value - baseline) / std
        else:
            z = 0
        if z >= 3:
            magnitude = 90
        elif z >= 2:
            magnitude = 70
        elif z >= 1:
            magnitude = 50
        elif z >= 0.5:
            magnitude = 30
        else:
            magnitude = 10
        breakdown["signal_magnitude"] = magnitude

        # 3. Time Sensitivity (freshness relative to half-life)
        ts_str = signal.get("timestamp", "")
        half_life_hours = signal.get("half_life_hours", 48)
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
            half_lives_elapsed = age_hours / max(half_life_hours, 1)
        except (ValueError, TypeError):
            half_lives_elapsed = 3  # treat unparseable as stale

        if half_lives_elapsed < 0.5:
            freshness = 95
        elif half_lives_elapsed < 1:
            freshness = 75
        elif half_lives_elapsed < 2:
            freshness = 50
        elif half_lives_elapsed < 3:
            freshness = 25
        else:
            freshness = 5
        breakdown["time_sensitivity"] = freshness

        # 4. Corroboration (count of independent confirming sources)
        corroborations = len(signal.get("corroborating_sources", []))
        if corroborations >= 3:
            corr_score = 90
        elif corroborations >= 2:
            corr_score = 70
        elif corroborations >= 1:
            corr_score = 50
        else:
            corr_score = 15
        breakdown["corroboration"] = corr_score

        # 5. Novelty
        is_novel = signal.get("is_novel", False)
        novelty = 85 if is_novel else 25
        breakdown["novelty"] = novelty

        # Weighted sum
        dim_map = {
            "source_credibility": "source_credibility",
            "signal_magnitude": "signal_magnitude",
            "time_sensitivity": "time_sensitivity",
            "corroboration": "corroboration",
            "novelty": "novelty",
        }
        total = 0.0
        for dim_key, weight in self.dimension_weights.items():
            total += breakdown.get(dim_map.get(dim_key, dim_key), 40) * weight

        score = round(total)
        score = max(0, min(100, score))

        # Determine bucket
        bucket = "noise"
        action = BUCKETS[-1][2]
        for min_score, bname, baction in BUCKETS:
            if score >= min_score:
                bucket = bname
                action = baction
                break

        return {
            "source_key": source_key,
            "name": signal.get("name", ""),
            "score": score,
            "bucket": bucket,
            "action": action,
            "breakdown": breakdown,
        }

    def score_batch(self, signals: list[dict]) -> list[dict]:
        """Score all signals, return sorted by score descending."""
        results = [self.score_signal(s) for s in signals]
        results.sort(key=lambda r: r["score"], reverse=True)
        return results

    def get_ensemble_weight(self, bucket: str) -> float:
        """Return the ensemble weight multiplier for a score bucket."""
        return {
            "exceptional": 1.5,
            "high": 1.0,
            "medium": 1.0,
            "low": 0.5,
            "noise": 0.0,
        }.get(bucket, 1.0)
```

### Step 4: Run tests

Run: `cd ~/Projects/polymarket-omega && python3.11 -m pytest tests/test_signal_scorer.py -xvs`
Expected: PASS

### Step 5: Integrate into probability_estimator.py

In `/Users/singularityjason/Projects/polymarket-omega/agents/probability_estimator.py`, add import near top:

```python
from lib.signal_scorer import SignalScorer
```

In `build_prompt()` (around line 1004), after signals are collected but before prompt construction, add scoring:

```python
# Score signals through rubric
scorer = SignalScorer()
signal_dicts = _format_signals_for_scoring(on_chain_data, mindshare_data, macro_data)
scored = scorer.score_batch(signal_dicts)

# Filter out noise, annotate prompt with scores
active_signals = [s for s in scored if s["bucket"] != "noise"]
signal_score_context = "\n".join(
    f"- {s['name']}: score={s['score']} ({s['bucket']}) weight={scorer.get_ensemble_weight(s['bucket'])}x"
    for s in active_signals
)
```

Add a helper function `_format_signals_for_scoring()` that converts the existing signal data dicts into the format expected by SignalScorer (source_key, value, baseline_value, baseline_std, timestamp, half_life_hours, corroborating_sources, is_novel).

Inject `signal_score_context` into the prompt after the signal weighting guide section (~line 268).

### Step 6: Save signal scores to daily file

In `run_estimation()` (~line 1422), after scoring, save:

```python
import json
from datetime import date

scores_path = f"data/signal_scores_{date.today().isoformat()}.json"
with open(scores_path, "w") as f:
    json.dump({"date": date.today().isoformat(), "signals": scored}, f, indent=2)
```

### Step 7: Add feedback loop to calibrator.py

In `/Users/singularityjason/Projects/polymarket-omega/agents/calibrator.py`, after `compute_signal_accuracy()` (~line 96), add a function that compares signal scores vs actual outcomes and adjusts source credibility baselines in the rubric:

```python
def update_source_baselines(signal_accuracy: dict, rubric_path: str = "config/signal_rubric.md") -> None:
    """Adjust source credibility baselines based on actual signal accuracy.

    If a source's signals led to correct predictions >60% of the time,
    bump its baseline by 2. If <40%, decrease by 2. Clamped to [20, 95].
    """
    text = Path(rubric_path).read_text()
    for source_key, stats in signal_accuracy.items():
        accuracy = stats.get("accuracy", 0.5)
        # Find and adjust the line in the rubric
        pattern = rf"(\|\s*{re.escape(source_key)}\s*\|\s*)(\d+)(\s*\|)"
        match = re.search(pattern, text)
        if match:
            current = int(match.group(2))
            if accuracy > 0.6:
                new_val = min(95, current + 2)
            elif accuracy < 0.4:
                new_val = max(20, current - 2)
            else:
                continue
            text = text[:match.start(2)] + str(new_val) + text[match.end(2):]
    Path(rubric_path).write_text(text)
```

Call this from `run_calibration()` on the weekly Sunday run.

### Step 8: Commit

```bash
cd ~/Projects/polymarket-omega
git add config/signal_rubric.md lib/signal_scorer.py tests/test_signal_scorer.py agents/probability_estimator.py agents/calibrator.py
git commit -m "feat: add signal scoring rubric with feedback loop

Editable markdown rubric at config/signal_rubric.md scores signals on
5 dimensions (credibility, magnitude, freshness, corroboration, novelty).
Scores drive ensemble weighting. Weekly calibration updates baselines."
```

---

## Task 3: Cron Infrastructure for Conductor

**Files:**
- Create: `/Users/singularityjason/Projects/conductor/src/conductor/engine/cron_manager.py`
- Create: `/Users/singularityjason/Projects/conductor/tests/test_cron_manager.py`
- Modify: `/Users/singularityjason/Projects/conductor/src/conductor/storage/journal.py` (add tables)

### Step 1: Write failing tests

Create `/Users/singularityjason/Projects/conductor/tests/test_cron_manager.py`:

```python
"""Tests for cron job management infrastructure."""
import os
import time
import pytest
import aiosqlite

from conductor.engine.cron_manager import CronManager


@pytest.fixture
async def cron_mgr(tmp_path):
    db_path = str(tmp_path / "test_conductor.db")
    mgr = CronManager(db_path=db_path)
    await mgr.initialize()
    yield mgr
    await mgr.close()


@pytest.mark.asyncio
async def test_log_start_returns_run_id(cron_mgr):
    run_id = await cron_mgr.log_start("daily_pipeline")
    assert isinstance(run_id, int)
    assert run_id > 0


@pytest.mark.asyncio
async def test_log_end_success(cron_mgr):
    run_id = await cron_mgr.log_start("daily_pipeline")
    await cron_mgr.log_end(run_id, "success", "completed ok")
    history = await cron_mgr.get_history("daily_pipeline")
    assert len(history) == 1
    assert history[0]["status"] == "success"
    assert history[0]["duration_seconds"] is not None


@pytest.mark.asyncio
async def test_should_run_idempotency(cron_mgr):
    # First run: should be allowed
    assert await cron_mgr.should_run("daily_pipeline", "1d") is True
    # Log a successful run
    run_id = await cron_mgr.log_start("daily_pipeline")
    await cron_mgr.log_end(run_id, "success")
    # Second run within interval: should be skipped
    assert await cron_mgr.should_run("daily_pipeline", "1d") is False


@pytest.mark.asyncio
async def test_should_run_allows_after_failure(cron_mgr):
    run_id = await cron_mgr.log_start("daily_pipeline")
    await cron_mgr.log_end(run_id, "failure", "crashed")
    # Should allow retry after failure
    assert await cron_mgr.should_run("daily_pipeline", "1d") is True


@pytest.mark.asyncio
async def test_acquire_release_lock(cron_mgr):
    assert await cron_mgr.acquire_lock("daily_pipeline") is True
    # Second acquire should fail (already locked by us)
    assert await cron_mgr.acquire_lock("daily_pipeline") is False
    await cron_mgr.release_lock("daily_pipeline")
    # After release, should succeed
    assert await cron_mgr.acquire_lock("daily_pipeline") is True


@pytest.mark.asyncio
async def test_cleanup_stale(cron_mgr):
    run_id = await cron_mgr.log_start("stuck_job")
    # Backdate to 3 hours ago
    await cron_mgr._db.execute(
        "UPDATE cron_runs SET started_at = datetime('now', '-3 hours') WHERE id = ?",
        (run_id,),
    )
    await cron_mgr._db.commit()
    cleaned = await cron_mgr.cleanup_stale(max_age_hours=2)
    assert cleaned > 0
    history = await cron_mgr.get_history("stuck_job")
    assert history[0]["status"] == "failure"


@pytest.mark.asyncio
async def test_detect_persistent_failures(cron_mgr):
    # Create 3 failures in quick succession
    for _ in range(3):
        run_id = await cron_mgr.log_start("flaky_job")
        await cron_mgr.log_end(run_id, "failure", "flaky error")
    assert await cron_mgr.detect_persistent_failures("flaky_job") is True


@pytest.mark.asyncio
async def test_context_manager(cron_mgr):
    async with cron_mgr.cron_job("ctx_test") as run:
        assert not run.skipped
        assert run.run_id > 0
    # Should be logged as success
    history = await cron_mgr.get_history("ctx_test")
    assert history[0]["status"] == "success"
```

Run: `cd ~/Projects/conductor && python -m pytest tests/test_cron_manager.py -xvs`
Expected: FAIL — module doesn't exist.

### Step 2: Implement CronManager

Create `/Users/singularityjason/Projects/conductor/src/conductor/engine/cron_manager.py`:

```python
"""Cron job management: logging, locking, idempotency, stale recovery.

Provides PID-based locking, run history, idempotency checks, and
persistent failure detection. Integrates with Conductor's circuit
breaker and dead letter queue for fault tolerance.
"""
import os
import signal
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS cron_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    summary TEXT,
    duration_seconds REAL,
    error_detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_cron_runs_job
    ON cron_runs(job_name, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_cron_runs_status
    ON cron_runs(status) WHERE status = 'running';

CREATE TABLE IF NOT EXISTS cron_locks (
    job_name TEXT PRIMARY KEY,
    pid INTEGER NOT NULL,
    acquired_at TEXT NOT NULL,
    hostname TEXT
);
"""

INTERVAL_SECONDS = {
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
}


@dataclass
class CronRun:
    run_id: int
    skipped: bool
    job_name: str


class CronManager:
    def __init__(self, db_path: str = "conductor.db"):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    async def log_start(self, job_name: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        # Clean up stale jobs on every start
        await self.cleanup_stale()
        cursor = await self._db.execute(
            "INSERT INTO cron_runs (job_name, started_at, status) VALUES (?, ?, 'running')",
            (job_name, now),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def log_end(self, run_id: int, status: str, summary: str = "", error_detail: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        row = await self._db.execute_fetchall(
            "SELECT started_at FROM cron_runs WHERE id = ?", (run_id,)
        )
        duration = None
        if row:
            started = datetime.fromisoformat(row[0][0])
            duration = (datetime.now(timezone.utc) - started).total_seconds()
        await self._db.execute(
            """UPDATE cron_runs
               SET completed_at = ?, status = ?, summary = ?,
                   duration_seconds = ?, error_detail = ?
               WHERE id = ?""",
            (now, status, summary, duration, error_detail, run_id),
        )
        await self._db.commit()

    async def should_run(self, job_name: str, interval: str) -> bool:
        seconds = INTERVAL_SECONDS.get(interval, 86400)
        rows = await self._db.execute_fetchall(
            """SELECT started_at FROM cron_runs
               WHERE job_name = ? AND status = 'success'
               ORDER BY started_at DESC LIMIT 1""",
            (job_name,),
        )
        if not rows:
            return True
        last = datetime.fromisoformat(rows[0][0])
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        return elapsed >= seconds

    async def acquire_lock(self, job_name: str) -> bool:
        pid = os.getpid()
        hostname = os.uname().nodename
        existing = await self._db.execute_fetchall(
            "SELECT pid FROM cron_locks WHERE job_name = ?", (job_name,)
        )
        if existing:
            old_pid = existing[0][0]
            if _pid_alive(old_pid):
                return False
            # Dead PID: steal the lock
            await self._db.execute(
                "DELETE FROM cron_locks WHERE job_name = ?", (job_name,)
            )
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT INTO cron_locks (job_name, pid, acquired_at, hostname) VALUES (?, ?, ?, ?)",
            (job_name, pid, now, hostname),
        )
        await self._db.commit()
        return True

    async def release_lock(self, job_name: str) -> None:
        await self._db.execute(
            "DELETE FROM cron_locks WHERE job_name = ?", (job_name,)
        )
        await self._db.commit()

    async def cleanup_stale(self, max_age_hours: int = 2) -> int:
        rows = await self._db.execute_fetchall(
            """SELECT id FROM cron_runs
               WHERE status = 'running'
                 AND started_at < datetime('now', ? || ' hours')""",
            (f"-{max_age_hours}",),
        )
        if not rows:
            return 0
        ids = [r[0] for r in rows]
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            f"""UPDATE cron_runs
                SET status = 'failure', completed_at = ?,
                    error_detail = 'Marked stale after {max_age_hours}h'
                WHERE id IN ({','.join('?' * len(ids))})""",
            [now] + ids,
        )
        await self._db.commit()
        return len(ids)

    async def detect_persistent_failures(
        self, job_name: str, window_hours: int = 6, threshold: int = 3
    ) -> bool:
        rows = await self._db.execute_fetchall(
            """SELECT COUNT(*) FROM cron_runs
               WHERE job_name = ? AND status = 'failure'
                 AND started_at > datetime('now', ? || ' hours')""",
            (job_name, f"-{window_hours}"),
        )
        return rows[0][0] >= threshold

    async def get_history(
        self, job_name: str | None = None, status: str | None = None, days: int = 7
    ) -> list[dict]:
        query = "SELECT * FROM cron_runs WHERE started_at > datetime('now', ? || ' days')"
        params: list = [f"-{days}"]
        if job_name:
            query += " AND job_name = ?"
            params.append(job_name)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY started_at DESC"
        rows = await self._db.execute_fetchall(query, params)
        cols = ["id", "job_name", "started_at", "completed_at", "status",
                "summary", "duration_seconds", "error_detail"]
        return [dict(zip(cols, row)) for row in rows]

    @asynccontextmanager
    async def cron_job(self, job_name: str, interval: str | None = None):
        if interval and not await self.should_run(job_name, interval):
            yield CronRun(run_id=0, skipped=True, job_name=job_name)
            return

        if not await self.acquire_lock(job_name):
            yield CronRun(run_id=0, skipped=True, job_name=job_name)
            return

        run_id = await self.log_start(job_name)
        run = CronRun(run_id=run_id, skipped=False, job_name=job_name)
        try:
            yield run
            await self.log_end(run_id, "success")
        except Exception as e:
            await self.log_end(run_id, "failure", error_detail=str(e))
            raise
        finally:
            await self.release_lock(job_name)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False
```

### Step 3: Run tests

Run: `cd ~/Projects/conductor && python -m pytest tests/test_cron_manager.py -xvs`
Expected: PASS

### Step 4: Commit

```bash
cd ~/Projects/conductor
git add src/conductor/engine/cron_manager.py tests/test_cron_manager.py
git commit -m "feat(engine): add cron job infrastructure

CronManager provides PID-based locking, idempotent run tracking,
stale job recovery, and persistent failure detection. Includes
async context manager for clean job lifecycle management."
```

---

## Task 4: LLM Usage Tracking in OMEGA

**Files:**
- Create: `/Users/singularityjason/Projects/omega/src/omega/usage_tracker.py`
- Modify: `/Users/singularityjason/Projects/omega/src/omega/coordination.py` (v11 table)
- Create: `/Users/singularityjason/Projects/omega/tests/test_usage_tracker.py`
- Create: `/Users/singularityjason/Projects/omega/website/app/api/admin/llm-usage/route.ts`

### Step 1: Write failing test

Create `/Users/singularityjason/Projects/omega/tests/test_usage_tracker.py`:

```python
"""Tests for LLM usage tracking."""
import pytest
from pathlib import Path


def test_log_call_and_query(tmp_path):
    from omega.usage_tracker import UsageTracker

    tracker = UsageTracker(db_path=str(tmp_path / "usage.db"))
    tracker.log_call(
        session_id="sess-123",
        tool_name="omega_store",
        model="claude-opus-4-6",
        input_tokens=1000,
        output_tokens=500,
        project="test",
    )
    usage = tracker.get_usage(days=1, group_by="model")
    assert len(usage) == 1
    assert usage[0]["model"] == "claude-opus-4-6"
    assert usage[0]["total_input_tokens"] == 1000
    assert usage[0]["total_output_tokens"] == 500
    tracker.close()


def test_cost_estimation(tmp_path):
    from omega.usage_tracker import UsageTracker

    tracker = UsageTracker(db_path=str(tmp_path / "usage.db"))
    tracker.log_call(
        session_id="sess-123",
        tool_name="omega_query",
        model="claude-opus-4-6",
        input_tokens=1_000_000,
        output_tokens=100_000,
    )
    cost = tracker.get_cost_estimate(days=30)
    # Opus: 15/M input + 75/M output = $15 + $7.50 = $22.50
    assert cost["total_usd"] > 20
    assert cost["total_usd"] < 25
    tracker.close()


def test_top_tools(tmp_path):
    from omega.usage_tracker import UsageTracker

    tracker = UsageTracker(db_path=str(tmp_path / "usage.db"))
    for i in range(5):
        tracker.log_call("s1", "omega_store", "claude-sonnet-4-6", 100, 50)
    for i in range(2):
        tracker.log_call("s1", "omega_query", "claude-sonnet-4-6", 200, 100)

    top = tracker.get_top_tools(days=1, limit=5)
    assert top[0]["tool_name"] == "omega_store"
    assert top[0]["call_count"] == 5
    tracker.close()


def test_local_embedding_zero_cost(tmp_path):
    from omega.usage_tracker import UsageTracker

    tracker = UsageTracker(db_path=str(tmp_path / "usage.db"))
    tracker.log_call("s1", "embed", "nomic-embed-text", 5000, 0)
    cost = tracker.get_cost_estimate(days=1)
    assert cost["total_usd"] == 0.0
    tracker.close()
```

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_usage_tracker.py -xvs`
Expected: FAIL — module doesn't exist.

### Step 2: Implement UsageTracker

Create `/Users/singularityjason/Projects/omega/src/omega/usage_tracker.py`:

```python
"""LLM usage and cost tracking.

Logs every LLM call with token counts, estimates costs per model,
and provides aggregated usage queries for the admin dashboard.
"""
import sqlite3
import threading
from datetime import datetime, timezone


MODEL_PRICING = {  # per 1M tokens (USD)
    "claude-opus-4-6": {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_write": 18.75},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75},
    "claude-haiku-4-5": {"input": 0.8, "output": 4.0, "cache_read": 0.08, "cache_write": 1.0},
    "nomic-embed-text": {"input": 0.0, "output": 0.0},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    tool_name TEXT NOT NULL,
    model TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'anthropic',
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_write_tokens INTEGER DEFAULT 0,
    estimated_cost_usd REAL DEFAULT 0.0,
    duration_ms INTEGER,
    project TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_llm_usage_session ON llm_usage(session_id);
CREATE INDEX IF NOT EXISTS idx_llm_usage_tool ON llm_usage(tool_name, created_at);
CREATE INDEX IF NOT EXISTS idx_llm_usage_created ON llm_usage(created_at);
"""


def _estimate_cost(model: str, input_tokens: int, output_tokens: int,
                   cache_read: int = 0, cache_write: int = 0) -> float:
    pricing = MODEL_PRICING.get(model, MODEL_PRICING.get("claude-sonnet-4-6", {}))
    cost = (
        input_tokens * pricing.get("input", 3.0) / 1_000_000
        + output_tokens * pricing.get("output", 15.0) / 1_000_000
        + cache_read * pricing.get("cache_read", 0.3) / 1_000_000
        + cache_write * pricing.get("cache_write", 3.75) / 1_000_000
    )
    return round(cost, 6)


class UsageTracker:
    def __init__(self, db_path: str | None = None):
        if db_path is None:
            from omega.sqlite_store import _default_db_dir
            db_path = str(_default_db_dir() / "llm_usage.db")
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self._lock = threading.Lock()

    def close(self) -> None:
        self._conn.close()

    def log_call(
        self,
        session_id: str | None,
        tool_name: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read: int = 0,
        cache_write: int = 0,
        duration_ms: int | None = None,
        project: str | None = None,
    ) -> None:
        provider = "local" if model.startswith("nomic") else "anthropic"
        cost = _estimate_cost(model, input_tokens, output_tokens, cache_read, cache_write)
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                """INSERT INTO llm_usage
                   (session_id, tool_name, model, provider, input_tokens, output_tokens,
                    cache_read_tokens, cache_write_tokens, estimated_cost_usd,
                    duration_ms, project, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, tool_name, model, provider, input_tokens, output_tokens,
                 cache_read, cache_write, cost, duration_ms, project, now),
            )
            self._conn.commit()

    def get_usage(self, days: int = 7, group_by: str = "model") -> list[dict]:
        valid_groups = {"model", "tool_name", "session_id", "project"}
        if group_by not in valid_groups:
            group_by = "model"
        with self._lock:
            rows = self._conn.execute(
                f"""SELECT {group_by},
                           SUM(input_tokens) as total_input_tokens,
                           SUM(output_tokens) as total_output_tokens,
                           SUM(estimated_cost_usd) as total_cost,
                           COUNT(*) as call_count
                    FROM llm_usage
                    WHERE created_at > datetime('now', '-' || ? || ' days')
                    GROUP BY {group_by}
                    ORDER BY total_cost DESC""",
                (days,),
            ).fetchall()
        return [
            {group_by: r[0], "total_input_tokens": r[1], "total_output_tokens": r[2],
             "total_cost_usd": r[3], "call_count": r[4]}
            for r in rows
        ]

    def get_cost_estimate(self, days: int = 30) -> dict:
        with self._lock:
            row = self._conn.execute(
                """SELECT SUM(estimated_cost_usd), SUM(input_tokens), SUM(output_tokens),
                          COUNT(*)
                   FROM llm_usage
                   WHERE created_at > datetime('now', '-' || ? || ' days')""",
                (days,),
            ).fetchone()
        return {
            "total_usd": round(row[0] or 0, 4),
            "total_input_tokens": row[1] or 0,
            "total_output_tokens": row[2] or 0,
            "total_calls": row[3] or 0,
            "period_days": days,
        }

    def get_top_tools(self, days: int = 7, limit: int = 10) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT tool_name,
                          SUM(input_tokens + output_tokens) as total_tokens,
                          SUM(estimated_cost_usd) as total_cost,
                          COUNT(*) as call_count
                   FROM llm_usage
                   WHERE created_at > datetime('now', '-' || ? || ' days')
                   GROUP BY tool_name
                   ORDER BY call_count DESC
                   LIMIT ?""",
                (days, limit),
            ).fetchall()
        return [
            {"tool_name": r[0], "total_tokens": r[1], "total_cost_usd": r[2], "call_count": r[3]}
            for r in rows
        ]
```

### Step 3: Run tests

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_usage_tracker.py -xvs`
Expected: PASS

### Step 4: Add admin API route

Create `/Users/singularityjason/Projects/omega/website/app/api/admin/llm-usage/route.ts`:

```typescript
import { NextRequest, NextResponse } from "next/server";
import { getOmegaClient } from "@/lib/omega-client";

export async function GET(req: NextRequest) {
  const days = Number(req.nextUrl.searchParams.get("days") ?? "7");
  const groupBy = req.nextUrl.searchParams.get("group_by") ?? "model";

  try {
    const client = getOmegaClient();
    const [usage, cost, topTools] = await Promise.all([
      client.query(`llm_usage_by_${groupBy}`, { days }),
      client.query("llm_cost_estimate", { days: 30 }),
      client.query("llm_top_tools", { days, limit: 10 }),
    ]);

    return NextResponse.json({
      usage: usage ?? [],
      cost: cost ?? { total_usd: 0 },
      topTools: topTools ?? [],
    });
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to fetch LLM usage data" },
      { status: 500 }
    );
  }
}
```

Note: The exact integration with the OMEGA client depends on how the admin dashboard currently fetches data. Check the pattern in existing routes like `/api/admin/dashboard/route.ts` and follow the same approach.

### Step 5: Commit

```bash
cd ~/Projects/omega
git add src/omega/usage_tracker.py tests/test_usage_tracker.py website/app/api/admin/llm-usage/route.ts
git commit -m "feat: add LLM usage and cost tracking

UsageTracker logs token counts per tool call, estimates costs from
per-model pricing, and provides aggregated queries for the admin
dashboard (by model, tool, session, or project)."
```

---

## Task 5: Nightly Self-Audit Council

**Files:**
- Create: `/Users/singularityjason/Projects/omega/src/omega/council.py`
- Create: `/Users/singularityjason/Projects/omega/config/councils/platform_health.md`
- Create: `/Users/singularityjason/Projects/omega/config/councils/security.md`
- Create: `/Users/singularityjason/Projects/omega/config/councils/innovation.md`
- Modify: `/Users/singularityjason/Projects/omega/src/omega/server/coord_handlers.py` (register tool)
- Modify: `/Users/singularityjason/Projects/omega/src/omega/server/coord_schemas.py` (add schema)
- Create: `/Users/singularityjason/Projects/omega/tests/test_council.py`

### Step 1: Create council prompt templates

Create `/Users/singularityjason/Projects/omega/config/councils/platform_health.md`:

```markdown
# Platform Health Council

You are a platform health reviewer for the OMEGA project. Analyze the provided signals and produce a structured health report.

## Input Signals
You will receive:
- Recent error memories (last 24h)
- Tool call audit data (failure rates)
- Memory store health metrics
- Cron job reliability stats (if available)

## Output Format
Produce a JSON object with:
- health_score: 0-100 integer
- issues: array of {severity: "critical"|"warning"|"info", description: string, evidence: string, suggested_fix: string}
- summary: 1-2 sentence overall assessment

## Focus Areas
- Error rate trends (increasing = critical)
- Memory store capacity and embedding quality
- Tool failures and timeout patterns
- Coordination deadlocks or stale sessions
- Database size growth rate
```

Create `/Users/singularityjason/Projects/omega/config/councils/security.md`:

```markdown
# Security Council

You are a security reviewer for the OMEGA project. Analyze stored data for security risks.

## Input Signals
You will receive:
- Recent memories that may contain credential patterns
- External action audit trail
- Memory content samples for injection pattern analysis

## Output Format
Produce a JSON object with:
- risk_score: 0-100 integer (higher = more risk)
- vulnerabilities: array of {severity: "critical"|"high"|"medium"|"low", type: string, description: string, remediation: string}
- summary: 1-2 sentence assessment

## Focus Areas
- Credential-like strings in stored memories (API keys, tokens, passwords)
- Prompt injection patterns in ingested content
- PII exposure in non-confidential contexts
- External actions taken without proper authorization checks
```

Create `/Users/singularityjason/Projects/omega/config/councils/innovation.md`:

```markdown
# Innovation Scout Council

You are an innovation scout reviewing the OMEGA project's capabilities. Identify opportunities for new automations and features.

## Input Signals
You will receive:
- Current tool inventory and usage patterns
- Entity and relationship data
- Recent decisions and lessons learned
- Community patterns and trends (if available)

## Output Format
Produce a JSON object with:
- proposals: array of {title: string, description: string, effort: "small"|"medium"|"large", impact: "low"|"medium"|"high", rationale: string}
- summary: 1-2 sentence overview

## Focus Areas
- Underutilized tools (registered but rarely called)
- Manual workflows that could be automated
- Cross-entity connections not yet exploited
- Patterns from other AI agent systems (OpenClaw, etc.)
```

### Step 2: Write failing test

Create `/Users/singularityjason/Projects/omega/tests/test_council.py`:

```python
"""Tests for the self-audit council system."""
import pytest
from pathlib import Path


def test_council_loads_prompt_template():
    from omega.council import Council

    c = Council(domain="platform_health")
    assert "Platform Health" in c.prompt_template
    assert "health_score" in c.prompt_template


def test_council_gathers_signals(tmp_path):
    from omega.council import Council

    c = Council(domain="platform_health", db_dir=str(tmp_path))
    signals = c.gather_signals(project="omega")
    assert isinstance(signals, dict)
    assert "recent_errors" in signals
    assert "health_metrics" in signals


def test_council_formats_prompt():
    from omega.council import Council

    c = Council(domain="platform_health")
    signals = {"recent_errors": [], "health_metrics": {"capacity_pct": 45}}
    prompt = c.format_prompt(signals)
    assert "capacity_pct" in prompt
    assert "Platform Health" in prompt


def test_council_unknown_domain_raises():
    from omega.council import Council

    with pytest.raises(FileNotFoundError):
        Council(domain="nonexistent_domain")


def test_all_domains_have_templates():
    from omega.council import COUNCIL_DOMAINS

    for domain in COUNCIL_DOMAINS:
        path = Path(__file__).parent.parent / "config" / "councils" / f"{domain}.md"
        assert path.exists(), f"Missing template: {path}"
```

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_council.py -xvs`
Expected: FAIL — module doesn't exist.

### Step 3: Implement Council

Create `/Users/singularityjason/Projects/omega/src/omega/council.py`:

```python
"""Self-audit council system.

Runs domain-specific analysis (platform health, security, innovation)
by gathering signals from OMEGA's memory and coordination systems,
then producing structured findings via LLM analysis.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

COUNCIL_DOMAINS = ("platform_health", "security", "innovation")

# Resolve config dir relative to package
_CONFIG_DIR = Path(__file__).parent.parent.parent / "config" / "councils"


class Council:
    def __init__(self, domain: str, config_dir: str | None = None, db_dir: str | None = None):
        if domain not in COUNCIL_DOMAINS:
            pass  # Allow custom domains if template exists
        self.domain = domain
        self._config_dir = Path(config_dir) if config_dir else _CONFIG_DIR
        self._db_dir = db_dir

        template_path = self._config_dir / f"{domain}.md"
        if not template_path.exists():
            raise FileNotFoundError(f"No council template at {template_path}")
        self.prompt_template = template_path.read_text()

    def gather_signals(self, project: str | None = None) -> dict[str, Any]:
        """Gather input signals for this council domain."""
        signals: dict[str, Any] = {}

        if self.domain == "platform_health":
            signals["recent_errors"] = self._query_recent_errors(project)
            signals["health_metrics"] = self._get_health_metrics()
            signals["tool_failure_rates"] = self._get_tool_failures(project)

        elif self.domain == "security":
            signals["credential_patterns"] = self._scan_credential_patterns()
            signals["external_actions"] = self._get_external_actions(project)
            signals["recent_content_samples"] = self._get_content_samples()

        elif self.domain == "innovation":
            signals["tool_usage"] = self._get_tool_usage()
            signals["recent_decisions"] = self._get_recent_decisions(project)
            signals["recent_lessons"] = self._get_recent_lessons(project)

        return signals

    def format_prompt(self, signals: dict[str, Any]) -> str:
        """Combine template with gathered signals into a complete prompt."""
        signals_text = json.dumps(signals, indent=2, default=str)
        return f"{self.prompt_template}\n\n## Signals Data\n\n```json\n{signals_text}\n```"

    def _query_recent_errors(self, project: str | None) -> list[dict]:
        try:
            from omega.bridge import query
            result = query(
                "recent errors and failures in last 24 hours",
                mode="recent",
                event_type="error_pattern",
                limit=20,
                project=project,
            )
            if isinstance(result, str):
                return [{"raw": result}]
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.debug("Failed to query errors: %s", e)
            return []

    def _get_health_metrics(self) -> dict:
        try:
            from omega.bridge import check_health
            return check_health()
        except Exception:
            return {}

    def _get_tool_failures(self, project: str | None) -> list:
        try:
            from omega.coordination import get_manager
            mgr = get_manager()
            # Query audit log for failures in last 24h
            with mgr._lock:
                rows = mgr._conn.execute(
                    """SELECT tool_name, COUNT(*) as fail_count
                       FROM coord_audit
                       WHERE result_summary LIKE '%error%'
                         AND created_at > datetime('now', '-1 day')
                       GROUP BY tool_name
                       ORDER BY fail_count DESC
                       LIMIT 10"""
                ).fetchall()
            return [{"tool": r[0], "failures": r[1]} for r in rows]
        except Exception:
            return []

    def _scan_credential_patterns(self) -> list:
        try:
            import re
            from omega.bridge import query
            result = query("recent stored content", mode="recent", limit=50)
            patterns = [
                r"sk-[a-zA-Z0-9]{20,}",
                r"key-[a-zA-Z0-9]{20,}",
                r"Bearer [a-zA-Z0-9\-._~+/]+=*",
                r"password\s*[:=]\s*\S+",
            ]
            findings = []
            content = result if isinstance(result, str) else str(result)
            for p in patterns:
                if re.search(p, content):
                    findings.append({"pattern": p, "found": True})
            return findings
        except Exception:
            return []

    def _get_external_actions(self, project: str | None) -> list:
        try:
            from omega.coordination import get_manager
            mgr = get_manager()
            with mgr._lock:
                rows = mgr._conn.execute(
                    """SELECT action_type, action_target, status, created_at
                       FROM coord_external_actions
                       WHERE created_at > datetime('now', '-1 day')
                       ORDER BY created_at DESC LIMIT 20"""
                ).fetchall()
            return [{"type": r[0], "target": r[1], "status": r[2], "at": r[3]} for r in rows]
        except Exception:
            return []

    def _get_content_samples(self) -> list:
        return []  # Placeholder: would sample recent ingested content

    def _get_tool_usage(self) -> list:
        try:
            from omega.coordination import get_manager
            mgr = get_manager()
            with mgr._lock:
                rows = mgr._conn.execute(
                    """SELECT tool_name, COUNT(*) as calls
                       FROM coord_audit
                       WHERE created_at > datetime('now', '-7 days')
                       GROUP BY tool_name
                       ORDER BY calls DESC"""
                ).fetchall()
            return [{"tool": r[0], "calls_7d": r[1]} for r in rows]
        except Exception:
            return []

    def _get_recent_decisions(self, project: str | None) -> list:
        try:
            from omega.bridge import query
            result = query("recent decisions", mode="recent", event_type="decision", limit=10, project=project)
            return [{"raw": result}] if isinstance(result, str) else (result or [])
        except Exception:
            return []

    def _get_recent_lessons(self, project: str | None) -> list:
        try:
            from omega.bridge import query
            result = query("recent lessons learned", mode="recent", event_type="lesson_learned", limit=10, project=project)
            return [{"raw": result}] if isinstance(result, str) else (result or [])
        except Exception:
            return []
```

### Step 4: Run tests

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_council.py -xvs`
Expected: PASS

### Step 5: Register MCP tool

In `/Users/singularityjason/Projects/omega/src/omega/server/coord_schemas.py`, add the omega_council schema:

```python
{
    "name": "omega_council",
    "description": "Run a self-audit council analysis. Domains: platform_health (error rates, capacity, tool failures), security (credential exposure, injection risks), innovation (unused capabilities, new feature ideas).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "description": "Council domain to run",
                "enum": ["platform_health", "security", "innovation"],
            },
            "project": {
                "type": "string",
                "description": "Scope to specific project (optional)",
            },
        },
        "required": ["domain"],
    },
},
```

In `/Users/singularityjason/Projects/omega/src/omega/server/coord_handlers.py`, add the handler:

```python
async def handle_council(arguments: dict) -> dict:
    """Run a self-audit council analysis."""
    domain = arguments.get("domain", "").strip()
    project = arguments.get("project")

    if domain not in ("platform_health", "security", "innovation"):
        return mcp_error("domain must be: platform_health, security, or innovation")

    try:
        from omega.council import Council

        council = Council(domain=domain)
        signals = council.gather_signals(project=project)
        prompt = council.format_prompt(signals)

        # Store the finding
        from omega.bridge import auto_capture
        auto_capture(
            content=f"[Council: {domain}] Signals gathered for analysis:\n{json.dumps(signals, default=str)[:2000]}",
            event_type="council_finding",
            metadata={"domain": domain, "project": project or "all"},
            project=project,
        )

        return mcp_response(
            f"## Council: {domain}\n\n"
            f"Signals gathered. Use the following prompt with your preferred model "
            f"to generate the analysis:\n\n```\n{prompt[:3000]}\n```\n\n"
            f"After review, store accepted findings with omega_store (event_type='decision') "
            f"or rejected ones with event_type='lesson_learned'."
        )
    except FileNotFoundError:
        return mcp_error(f"No template found for domain '{domain}'. Check config/councils/")
    except Exception as e:
        return mcp_error(f"Council failed: {e}")
```

Register it in the tool dispatch (wherever `handle_send_message` etc. are registered).

### Step 6: Run full test suite

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_council.py tests/test_coordination.py -x --timeout=60`
Expected: PASS

### Step 7: Commit

```bash
cd ~/Projects/omega
git add src/omega/council.py config/councils/ tests/test_council.py src/omega/server/coord_handlers.py src/omega/server/coord_schemas.py
git commit -m "feat: add self-audit council system (platform health, security, innovation)

Three council domains gather signals from OMEGA memory and coordination,
produce structured prompts for LLM analysis. Findings stored as
council_finding events with accept/reject feedback loop."
```

---

## Execution Order

Tasks are independent and can be executed in parallel across worktrees:

| Task | Project | Estimated Steps | Dependencies |
|------|---------|----------------|--------------|
| 1. Notification Batching | OMEGA | 14 steps | None |
| 2. Signal Scoring Rubric | polymarket-omega | 8 steps | None |
| 3. Cron Infrastructure | Conductor | 4 steps | None |
| 4. LLM Usage Tracking | OMEGA | 5 steps | Task 1 (shares v11 migration) |
| 5. Self-Audit Council | OMEGA | 7 steps | None (uses notification batching if available) |

**Note:** Tasks 1 and 4 both modify OMEGA's coordination.py. If running in parallel, Task 4's schema additions should be merged into Task 1's v11 migration.
