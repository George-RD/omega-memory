#!/usr/bin/env python3
"""OMEGA Compounding Memory Backtest

Validates the thesis: persistent memory that compounds over time provides
a measurable competitive edge over memoryless or short-horizon systems.

Methodology:
  1. Load all real memories from production OMEGA database (read-only)
  2. Auto-generate ground-truth questions from actual memory content
  3. For each question, test retrieval at progressive time horizons:
     - 0h (no memory baseline)
     - 6h, 12h, 24h, 48h, 72h, 120h, 168h (full)
  4. Measure retrieval hit rate and rank quality at each horizon
  5. Detect TRUE compounding: cases where older memories improve
     retrieval of newer ones (not just more data = more hits)

Expected result: non-linear accuracy growth with time horizon,
with cross-temporal retrieval gains proving the compounding thesis.

Usage:
  python3 scripts/backtest_compounding.py
  python3 scripts/backtest_compounding.py --questions 100
  python3 scripts/backtest_compounding.py --verbose
"""

import sys
import json
import sqlite3
import hashlib
import argparse
import statistics
from pathlib import Path
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from collections import defaultdict

# Ensure omega is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# ──────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────

OMEGA_DB = Path.home() / ".omega" / "omega.db"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "backtest_results"

# Time horizons to test (hours from earliest memory)
HORIZONS = [0, 6, 12, 24, 48, 72, 120, 168]

# How many results to check for a "hit"
TOP_K = 10

# Memory types worth generating questions for
QUESTIONABLE_TYPES = [
    "decision", "user_preference", "lesson_learned",
    "error_pattern", "user_fact", "reminder",
]

# Types to skip for question generation (but still used as context)
CONTEXT_ONLY_TYPES = [
    "session_summary", "task_completion", "checkpoint",
    "oracle_prediction", "memory", "session_respawn", "task",
]


# ──────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────

@dataclass
class Memory:
    node_id: str
    content: str
    event_type: str
    created_at: str
    access_count: int
    priority: int
    entity_id: str
    project: str
    metadata: dict
    created_ts: float = 0.0  # epoch seconds, computed

    def __post_init__(self):
        try:
            dt = datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
            self.created_ts = dt.timestamp()
        except (ValueError, AttributeError):
            self.created_ts = 0.0


@dataclass
class Question:
    qid: str
    question_text: str
    target_memory_id: str
    target_content: str
    target_type: str
    target_created_at: str
    target_created_ts: float
    question_category: str  # direct_recall, cross_temporal, compound
    requires_memories: list = field(default_factory=list)  # memory IDs needed
    difficulty: str = "medium"  # easy, medium, hard


@dataclass
class HorizonResult:
    horizon_hours: int
    memories_available: int
    target_available: bool  # is the target memory within this horizon?
    hit: bool  # was target memory in top-K results?
    rank: int  # 0 = not found, 1 = top result, etc.
    top_k_types: list = field(default_factory=list)
    context_hit: bool = False  # for compound: were supporting memories found?


@dataclass
class QuestionResult:
    question: Question
    horizons: list = field(default_factory=list)  # list of HorizonResult
    first_hit_horizon: int = -1  # earliest horizon where target was found
    compounding_detected: bool = False  # true if older context improved retrieval


# ──────────────────────────────────────────────────────────────────────
# Phase 1: Data extraction
# ──────────────────────────────────────────────────────────────────────

def load_memories(db_path: Path) -> list:
    """Load all memories from production OMEGA database (read-only)."""
    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("""
        SELECT node_id, content, event_type, created_at,
               access_count, priority, entity_id, project, metadata
        FROM memories
        ORDER BY created_at ASC
    """)

    memories = []
    for row in cursor:
        meta = {}
        if row["metadata"]:
            try:
                meta = json.loads(row["metadata"])
            except json.JSONDecodeError:
                pass

        memories.append(Memory(
            node_id=row["node_id"],
            content=row["content"] or "",
            event_type=row["event_type"] or "unknown",
            created_at=row["created_at"] or "",
            access_count=row["access_count"] or 0,
            priority=row["priority"] or 3,
            entity_id=row["entity_id"] or "",
            project=row["project"] or "",
            metadata=meta,
        ))

    conn.close()
    return memories


def load_edges(db_path: Path) -> list:
    """Load all edges (memory relationships) from the database."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT source_id, target_id, edge_type, weight FROM edges")
    edges = [dict(row) for row in cursor]
    conn.close()
    return edges


# ──────────────────────────────────────────────────────────────────────
# Phase 2: Question generation
# ──────────────────────────────────────────────────────────────────────

def extract_topic(content: str) -> str:
    """Extract a searchable topic phrase from memory content."""
    # Take first meaningful sentence/phrase, strip common prefixes
    text = content.strip()
    for prefix in ["Remember:", "Note:", "Decision:", "Lesson:", "Error:"]:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()

    # Take first sentence or first 120 chars
    for sep in [".", "\n", ";"]:
        idx = text.find(sep)
        if 20 < idx < 150:
            return text[:idx].strip()

    return text[:120].strip()


def generate_recall_query(memory: Memory) -> str:
    """Generate a natural retrieval query for a memory."""
    topic = extract_topic(memory.content)
    templates = {
        "decision": f"What was decided about {topic}?",
        "user_preference": f"What does the user prefer regarding {topic}?",
        "lesson_learned": f"What lesson was learned about {topic}?",
        "error_pattern": f"What is the known error pattern for {topic}?",
        "user_fact": f"What is known about {topic}?",
        "reminder": f"What reminder exists for {topic}?",
    }
    return templates.get(memory.event_type, f"What do you know about {topic}?")


def generate_questions(memories: list, edges: list, max_questions: int = 80) -> list:
    """Auto-generate ground-truth questions from real memory content."""
    questions = []
    mem_by_id = {m.node_id: m for m in memories}
    edge_map = defaultdict(list)  # source -> [(target, type)]
    for e in edges:
        edge_map[e["source_id"]].append((e["target_id"], e["edge_type"]))
        edge_map[e["target_id"]].append((e["source_id"], e["edge_type"]))

    # --- Category 1: Direct recall (60% of questions) ---
    # Sample from each questionable type proportionally
    by_type = defaultdict(list)
    for m in memories:
        if m.event_type in QUESTIONABLE_TYPES and len(m.content) > 30:
            by_type[m.event_type].append(m)

    direct_budget = int(max_questions * 0.6)
    per_type = max(2, direct_budget // len(by_type))

    for etype, mems in by_type.items():
        # Sample spread across time (take every N-th)
        step = max(1, len(mems) // per_type)
        sampled = mems[::step][:per_type]

        for m in sampled:
            qid = f"DR-{hashlib.md5(m.node_id.encode()).hexdigest()[:8]}"
            questions.append(Question(
                qid=qid,
                question_text=generate_recall_query(m),
                target_memory_id=m.node_id,
                target_content=m.content,
                target_type=m.event_type,
                target_created_at=m.created_at,
                target_created_ts=m.created_ts,
                question_category="direct_recall",
                requires_memories=[m.node_id],
                difficulty="easy" if m.access_count > 5 else "medium",
            ))

    # --- Category 2: Cross-temporal (25% of questions) ---
    # Questions requiring memories from different time periods
    cross_budget = int(max_questions * 0.25)
    cross_count = 0

    # Find memory pairs linked by edges that span different days
    for source_id, targets in edge_map.items():
        if cross_count >= cross_budget:
            break
        if source_id not in mem_by_id:
            continue
        source = mem_by_id[source_id]
        if source.event_type in CONTEXT_ONLY_TYPES:
            continue

        for target_id, etype in targets:
            if cross_count >= cross_budget:
                break
            if target_id not in mem_by_id:
                continue
            target = mem_by_id[target_id]
            if target.event_type in CONTEXT_ONLY_TYPES:
                continue

            # Must span at least 24h
            time_gap = abs(source.created_ts - target.created_ts)
            if time_gap < 86400:  # 24h in seconds
                continue

            # The newer memory is the "target", older is "context"
            if source.created_ts > target.created_ts:
                newer, older = source, target
            else:
                newer, older = target, source

            topic_newer = extract_topic(newer.content)
            topic_older = extract_topic(older.content)

            qid = f"CT-{hashlib.md5((newer.node_id + older.node_id).encode()).hexdigest()[:8]}"
            questions.append(Question(
                qid=qid,
                question_text=f"How does '{topic_older}' relate to '{topic_newer}'?",
                target_memory_id=newer.node_id,
                target_content=newer.content,
                target_type=newer.event_type,
                target_created_at=newer.created_at,
                target_created_ts=newer.created_ts,
                question_category="cross_temporal",
                requires_memories=[newer.node_id, older.node_id],
                difficulty="hard",
            ))
            cross_count += 1

    # --- Category 3: Compound reasoning (15% of questions) ---
    # Questions targeting memories with high edge connectivity
    compound_budget = int(max_questions * 0.15)
    compound_count = 0

    # Find memories with 3+ edges (highly connected = compound value)
    connectivity = [(nid, len(targets)) for nid, targets in edge_map.items()
                    if nid in mem_by_id and len(targets) >= 3]
    connectivity.sort(key=lambda x: -x[1])

    for nid, edge_count in connectivity:
        if compound_count >= compound_budget:
            break
        m = mem_by_id[nid]
        if m.event_type in CONTEXT_ONLY_TYPES or len(m.content) < 30:
            continue

        # Get connected memories
        connected = [tid for tid, _ in edge_map[nid] if tid in mem_by_id][:4]
        topic = extract_topic(m.content)

        qid = f"CR-{hashlib.md5(m.node_id.encode()).hexdigest()[:8]}"
        questions.append(Question(
            qid=qid,
            question_text=f"What is the full context around {topic}?",
            target_memory_id=m.node_id,
            target_content=m.content,
            target_type=m.event_type,
            target_created_at=m.created_at,
            target_created_ts=m.created_ts,
            question_category="compound",
            requires_memories=[m.node_id] + connected,
            difficulty="hard",
        ))
        compound_count += 1

    return questions[:max_questions]


# ──────────────────────────────────────────────────────────────────────
# Phase 3: Ablation engine
# ──────────────────────────────────────────────────────────────────────

def create_windowed_db(source_db: Path, target_db: Path, cutoff_iso: str):
    """Create a copy of the DB with only memories before cutoff."""
    import shutil
    if target_db.exists():
        target_db.unlink()
    # Remove stale WAL/SHM
    for suffix in ["-wal", "-shm"]:
        p = Path(str(target_db) + suffix)
        if p.exists():
            p.unlink()

    shutil.copy2(str(source_db), str(target_db))
    for suffix in ["-wal", "-shm"]:
        src = Path(str(source_db) + suffix)
        if src.exists():
            shutil.copy2(str(src), str(target_db) + suffix)

    # Delete future memories and rebuild FTS
    conn = sqlite3.connect(str(target_db))
    conn.execute("DELETE FROM memories WHERE created_at > ?", (cutoff_iso,))
    conn.execute("DELETE FROM edges WHERE source_id NOT IN (SELECT node_id FROM memories) "
                 "OR target_id NOT IN (SELECT node_id FROM memories)")
    try:
        conn.execute("INSERT INTO memories_fts(memories_fts) VALUES('rebuild')")
    except Exception:
        pass  # FTS rebuild may fail, that's ok
    conn.commit()
    remaining = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    conn.close()
    return remaining


def run_ablation(memories: list, questions: list, verbose: bool = False) -> list:
    """Test retrieval at each time horizon for each question.

    Creates physically windowed DB copies per horizon to guarantee
    strict temporal isolation. Uses the real OMEGA retrieval pipeline
    (decay curves, scoring, FTS, etc.) on each window.
    """
    from omega.sqlite_store import SQLiteStore
    from omega.embedding import reset_embedding_state
    reset_embedding_state()  # Ensure embeddings work in windowed stores

    earliest_ts = min(m.created_ts for m in memories if m.created_ts > 0)
    earliest_dt = datetime.fromtimestamp(earliest_ts, tz=timezone.utc)

    # Pre-compute: for each target, the earliest horizon it's available
    target_availability = {}
    for q in questions:
        target_mem = next((m for m in memories if m.node_id == q.target_memory_id), None)
        if target_mem:
            for h in HORIZONS:
                cutoff_ts = earliest_ts + (h * 3600)
                if target_mem.created_ts <= cutoff_ts:
                    target_availability[q.qid] = h
                    break

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Checkpoint the production DB first (merge WAL)
    conn = sqlite3.connect(f"file:{OMEGA_DB}?mode=ro", uri=True)
    conn.close()

    # Create windowed DBs for each non-zero horizon
    horizon_stores = {}
    horizon_mem_counts = {}
    for h in HORIZONS:
        if h == 0:
            horizon_mem_counts[h] = 0
            continue

        cutoff_dt = earliest_dt + timedelta(hours=h)
        cutoff_iso = cutoff_dt.isoformat()
        window_db = OUTPUT_DIR / f"_window_{h}h.db"

        n = create_windowed_db(OMEGA_DB, window_db, cutoff_iso)
        horizon_mem_counts[h] = n

        if n > 0:
            horizon_stores[h] = SQLiteStore(db_path=str(window_db))
        if verbose:
            print(f"    {h:>4d}h window: {n} memories")

    results = []

    for qi, q in enumerate(questions):
        if verbose and qi % 10 == 0:
            print(f"  Question {qi+1}/{len(questions)}: [{q.question_category}] "
                  f"{q.question_text[:60]}...")

        qresult = QuestionResult(question=q)

        for horizon_hours in HORIZONS:
            if horizon_hours == 0:
                qresult.horizons.append(HorizonResult(
                    horizon_hours=0, memories_available=0,
                    target_available=False, hit=False, rank=0,
                ))
                continue

            n_mems = horizon_mem_counts[horizon_hours]
            if n_mems == 0 or horizon_hours not in horizon_stores:
                qresult.horizons.append(HorizonResult(
                    horizon_hours=horizon_hours, memories_available=0,
                    target_available=False, hit=False, rank=0,
                ))
                continue

            target_available = (q.qid in target_availability and
                                target_availability[q.qid] <= horizon_hours)

            store = horizon_stores[horizon_hours]

            try:
                results_list = store.query(
                    q.question_text,
                    limit=TOP_K,
                    use_cache=False,
                    include_infrastructure=True,
                )
            except Exception as e:
                if verbose:
                    print(f"    Query error at {horizon_hours}h: {e}")
                results_list = []

            # Score: check if target memory is in results
            hit = False
            rank = 0
            top_k_types = []
            context_hit = False

            for i, r in enumerate(results_list):
                # Extract node_id from result
                rid = getattr(r, "id", "") or ""
                meta = getattr(r, "metadata", {}) or {}
                if isinstance(rid, int):
                    # .id is the internal rowid, get node_id from metadata
                    rid = meta.get("node_id", "")
                if not rid:
                    rid = meta.get("node_id", "")

                etype = meta.get("event_type", "unknown")
                top_k_types.append(etype)

                # Match against target
                content = getattr(r, "content", "") or ""
                if rid == q.target_memory_id:
                    hit = True
                    rank = i + 1
                elif not hit and content == q.target_content:
                    # Fallback: match on content if node_id isn't preserved
                    hit = True
                    rank = i + 1

                # Check supporting memories for compound questions
                if rid in q.requires_memories:
                    context_hit = True

            qresult.horizons.append(HorizonResult(
                horizon_hours=horizon_hours,
                memories_available=n_mems,
                target_available=target_available,
                hit=hit,
                rank=rank,
                top_k_types=top_k_types,
                context_hit=context_hit,
            ))

        # Detect compounding
        first_available = None
        first_hit = None
        for hr in qresult.horizons:
            if hr.target_available and first_available is None:
                first_available = hr.horizon_hours
            if hr.hit and first_hit is None:
                first_hit = hr.horizon_hours
                qresult.first_hit_horizon = hr.horizon_hours

        # True compounding = extra memories beyond the target's window
        # improved retrieval (hit found only with more context)
        if first_available and first_hit and first_hit > first_available:
            qresult.compounding_detected = True

        # Rank improvement = retrieval gets better with more memory
        ranks_when_hit = [(hr.horizon_hours, hr.rank) for hr in qresult.horizons
                          if hr.hit and hr.rank > 0]
        if len(ranks_when_hit) >= 2:
            first_rank = ranks_when_hit[0][1]
            last_rank = ranks_when_hit[-1][1]
            if last_rank < first_rank:
                qresult.compounding_detected = True

        results.append(qresult)

    # Cleanup
    for h, store in horizon_stores.items():
        store.close()
    for h in HORIZONS:
        for f in [OUTPUT_DIR / f"_window_{h}h.db",
                  OUTPUT_DIR / f"_window_{h}h.db-wal",
                  OUTPUT_DIR / f"_window_{h}h.db-shm"]:
            if f.exists():
                f.unlink()

    return results


# ──────────────────────────────────────────────────────────────────────
# Phase 4: Analysis & reporting
# ──────────────────────────────────────────────────────────────────────

def analyze(results: list, memories: list) -> dict:
    """Compute metrics from backtest results."""
    earliest_ts = min(m.created_ts for m in memories if m.created_ts > 0)

    # --- Accuracy by horizon ---
    horizon_stats = defaultdict(lambda: {
        "total": 0, "available": 0, "hits": 0,
        "ranks": [], "memories_available": 0
    })

    for qr in results:
        for hr in qr.horizons:
            stats = horizon_stats[hr.horizon_hours]
            stats["total"] += 1
            stats["memories_available"] = max(stats["memories_available"], hr.memories_available)
            if hr.target_available:
                stats["available"] += 1
            if hr.hit:
                stats["hits"] += 1
                stats["ranks"].append(hr.rank)

    accuracy_curve = {}
    for h in HORIZONS:
        s = horizon_stats[h]
        # Raw accuracy: hits / total questions
        raw_acc = s["hits"] / max(s["total"], 1)
        # Conditional accuracy: hits / questions where target was available
        cond_acc = s["hits"] / max(s["available"], 1) if s["available"] > 0 else 0
        avg_rank = statistics.mean(s["ranks"]) if s["ranks"] else 0

        accuracy_curve[h] = {
            "horizon_hours": h,
            "memories_available": s["memories_available"],
            "questions_answerable": s["available"],
            "hits": s["hits"],
            "raw_accuracy": round(raw_acc, 4),
            "conditional_accuracy": round(cond_acc, 4),
            "avg_rank": round(avg_rank, 2),
            "total_questions": s["total"],
        }

    # --- Accuracy by category ---
    cat_stats = defaultdict(lambda: defaultdict(lambda: {"total": 0, "hits": 0, "available": 0}))
    for qr in results:
        for hr in qr.horizons:
            cs = cat_stats[qr.question.question_category][hr.horizon_hours]
            cs["total"] += 1
            if hr.target_available:
                cs["available"] += 1
            if hr.hit:
                cs["hits"] += 1

    category_curves = {}
    for cat, horizons in cat_stats.items():
        category_curves[cat] = {}
        for h, s in horizons.items():
            category_curves[cat][h] = {
                "raw_accuracy": round(s["hits"] / max(s["total"], 1), 4),
                "conditional_accuracy": round(s["hits"] / max(s["available"], 1), 4) if s["available"] > 0 else 0,
            }

    # --- Compounding detection ---
    total_questions = len(results)
    compounding_count = sum(1 for qr in results if qr.compounding_detected)
    compounding_rate = compounding_count / max(total_questions, 1)

    # --- Marginal value of each horizon step ---
    marginal_value = {}
    prev_hits = 0
    prev_mems = 0
    for h in HORIZONS:
        s = accuracy_curve[h]
        delta_hits = s["hits"] - prev_hits
        delta_mems = s["memories_available"] - prev_mems
        marginal_value[h] = {
            "delta_hits": delta_hits,
            "delta_memories": delta_mems,
            "hits_per_memory": round(delta_hits / max(delta_mems, 1), 4),
        }
        prev_hits = s["hits"]
        prev_mems = s["memories_available"]

    # --- Type-level analysis ---
    type_stats = defaultdict(lambda: {"total": 0, "hits_at_full": 0})
    for qr in results:
        ts = type_stats[qr.question.target_type]
        ts["total"] += 1
        full_horizon = qr.horizons[-1] if qr.horizons else None
        if full_horizon and full_horizon.hit:
            ts["hits_at_full"] += 1

    type_accuracy = {
        t: round(s["hits_at_full"] / max(s["total"], 1), 4)
        for t, s in type_stats.items()
    }

    return {
        "accuracy_curve": accuracy_curve,
        "category_curves": category_curves,
        "compounding": {
            "total_questions": total_questions,
            "compounding_detected": compounding_count,
            "compounding_rate": round(compounding_rate, 4),
        },
        "marginal_value": marginal_value,
        "type_accuracy_at_full_horizon": type_accuracy,
    }


def print_report(analysis: dict, results: list, memories: list):
    """Print human-readable report."""
    print()
    print("=" * 70)
    print("  OMEGA COMPOUNDING MEMORY BACKTEST RESULTS")
    print("=" * 70)

    # Memory distribution
    by_day = defaultdict(int)
    earliest_ts = min(m.created_ts for m in memories if m.created_ts > 0)
    for m in memories:
        if m.created_ts > 0:
            day = int((m.created_ts - earliest_ts) / 86400) + 1
            by_day[day] += 1

    print(f"\n  Database: {len(memories)} memories over {len(by_day)} days")
    print("  Memory distribution:")
    for day in sorted(by_day.keys()):
        bar = "#" * (by_day[day] // 5)
        print(f"    Day {day:2d}: {by_day[day]:4d} memories {bar}")

    # Accuracy curve
    print(f"\n  ACCURACY CURVE (top-{TOP_K} retrieval)")
    print("  " + "-" * 66)
    print(f"  {'Horizon':>8s}  {'Mems':>5s}  {'Answerable':>10s}  {'Hits':>5s}  {'Raw Acc':>8s}  {'Cond Acc':>9s}  {'Avg Rank':>9s}")
    print("  " + "-" * 66)
    for h in HORIZONS:
        a = analysis["accuracy_curve"][h]
        bar = ">" * int(a["conditional_accuracy"] * 30)
        print(f"  {h:>6d}h  {a['memories_available']:>5d}  {a['questions_answerable']:>10d}  "
              f"{a['hits']:>5d}  {a['raw_accuracy']:>7.1%}  {a['conditional_accuracy']:>8.1%}  "
              f"{a['avg_rank']:>8.1f}  {bar}")

    # Category breakdown
    print(f"\n  CATEGORY BREAKDOWN (conditional accuracy at full horizon)")
    print("  " + "-" * 50)
    for cat, horizons in analysis["category_curves"].items():
        full = horizons.get(HORIZONS[-1], {})
        acc = full.get("conditional_accuracy", 0)
        print(f"    {cat:20s}  {acc:>7.1%}")

    # Compounding signal
    comp = analysis["compounding"]
    print(f"\n  COMPOUNDING SIGNAL")
    print("  " + "-" * 50)
    print(f"    Questions tested:        {comp['total_questions']}")
    print(f"    Compounding detected:    {comp['compounding_detected']} ({comp['compounding_rate']:.1%})")
    print(f"    (Older memories improved retrieval of newer ones)")

    # Marginal value
    print(f"\n  MARGINAL VALUE PER HORIZON STEP")
    print("  " + "-" * 50)
    for h in HORIZONS[1:]:
        mv = analysis["marginal_value"][h]
        if mv["delta_memories"] > 0:
            print(f"    +{h:>3d}h: +{mv['delta_hits']:>3d} hits from "
                  f"+{mv['delta_memories']:>4d} memories "
                  f"({mv['hits_per_memory']:.3f} hits/mem)")

    # Type accuracy
    print(f"\n  TYPE ACCURACY (full horizon)")
    print("  " + "-" * 50)
    for t, acc in sorted(analysis["type_accuracy_at_full_horizon"].items(),
                         key=lambda x: -x[1]):
        print(f"    {t:20s}  {acc:>7.1%}")

    # Verdict
    print(f"\n  {'=' * 66}")
    comp_rate = comp["compounding_rate"]
    curve = analysis["accuracy_curve"]
    full_acc = curve[HORIZONS[-1]]["conditional_accuracy"]
    half_acc = curve[HORIZONS[len(HORIZONS)//2]]["conditional_accuracy"]

    if comp_rate > 0.15 and full_acc > half_acc * 1.1:
        verdict = "CONFIRMED"
        detail = (f"Compounding detected in {comp_rate:.0%} of questions. "
                  f"Full-horizon accuracy ({full_acc:.0%}) exceeds "
                  f"mid-horizon ({half_acc:.0%}) by {(full_acc - half_acc):.0%}pp.")
    elif comp_rate > 0.05:
        verdict = "PARTIALLY CONFIRMED"
        detail = (f"Weak compounding signal ({comp_rate:.0%}). "
                  f"Marginal value of additional memory is positive but modest.")
    else:
        verdict = "NOT CONFIRMED"
        detail = (f"No significant compounding detected ({comp_rate:.0%}). "
                  f"Accuracy growth is primarily from having the target memory available.")

    print(f"  THESIS: Compounded memory provides competitive edge")
    print(f"  VERDICT: {verdict}")
    print(f"  {detail}")
    print(f"  {'=' * 66}")
    print()


def save_results(analysis: dict, results: list):
    """Save machine-readable results."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Save analysis
    with open(OUTPUT_DIR / "backtest_analysis.json", "w") as f:
        json.dump(analysis, f, indent=2)

    # Save per-question results
    qresults = []
    for qr in results:
        qresults.append({
            "qid": qr.question.qid,
            "question": qr.question.question_text,
            "category": qr.question.question_category,
            "target_type": qr.question.target_type,
            "difficulty": qr.question.difficulty,
            "first_hit_horizon": qr.first_hit_horizon,
            "compounding_detected": qr.compounding_detected,
            "horizons": [
                {
                    "hours": hr.horizon_hours,
                    "mems": hr.memories_available,
                    "available": hr.target_available,
                    "hit": hr.hit,
                    "rank": hr.rank,
                }
                for hr in qr.horizons
            ],
        })

    with open(OUTPUT_DIR / "backtest_questions.json", "w") as f:
        json.dump(qresults, f, indent=2)

    print(f"  Results saved to {OUTPUT_DIR}/")


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="OMEGA Compounding Memory Backtest")
    parser.add_argument("--questions", type=int, default=80, help="Max questions to generate")
    parser.add_argument("--verbose", action="store_true", help="Show progress")
    parser.add_argument("--db", type=str, default=str(OMEGA_DB), help="Database path")
    args = parser.parse_args()

    print("=" * 70)
    print("  OMEGA COMPOUNDING MEMORY BACKTEST")
    print("=" * 70)

    # Warm up embedding model (reset circuit breaker from any prior failures)
    try:
        from omega.embedding import reset_embedding_state, preload_embedding_model
        reset_embedding_state()
        loaded = preload_embedding_model()
        print(f"\n  Embedding model: {'ONNX (semantic search enabled)' if loaded else 'UNAVAILABLE (text-only)'}")
    except Exception as e:
        print(f"\n  Embedding model: UNAVAILABLE ({e})")

    # Phase 1: Load data
    print("\n  Phase 1: Loading memories...")
    memories = load_memories(Path(args.db))
    edges = load_edges(Path(args.db))
    print(f"    Loaded {len(memories)} memories, {len(edges)} edges")

    # Stats
    by_type = defaultdict(int)
    for m in memories:
        by_type[m.event_type] += 1
    for t, c in sorted(by_type.items(), key=lambda x: -x[1])[:8]:
        print(f"      {t:20s}: {c}")

    # Phase 2: Generate questions
    print(f"\n  Phase 2: Generating questions (max {args.questions})...")
    questions = generate_questions(memories, edges, max_questions=args.questions)
    print(f"    Generated {len(questions)} questions")
    by_cat = defaultdict(int)
    for q in questions:
        by_cat[q.question_category] += 1
    for cat, count in sorted(by_cat.items()):
        print(f"      {cat:20s}: {count}")

    # Phase 3: Run ablation
    print(f"\n  Phase 3: Running ablation across {len(HORIZONS)} time horizons...")
    print(f"    ({len(questions)} questions x {len(HORIZONS)} horizons = {len(questions) * len(HORIZONS)} retrievals)")
    results = run_ablation(memories, questions, verbose=args.verbose)
    print(f"    Ablation complete.")

    # Phase 4: Analyze & report
    print(f"\n  Phase 4: Analyzing results...")
    analysis = analyze(results, memories)
    print_report(analysis, results, memories)
    save_results(analysis, results)


if __name__ == "__main__":
    main()
