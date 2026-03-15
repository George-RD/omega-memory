#!/usr/bin/env python3
"""Say/Do POC: N-way comparison of entity contradiction profiles.

Loads all available entity DBs and generates a comparative analysis.
Add new entities by running their poc_saydo_<name>.py script first.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omega.sqlite_store import SQLiteStore
from omega.saydo.engine import get_saydo_engine, _normalize_entity
import omega.saydo.engine as eng_mod
import omega.bridge as bridge
from omega.saydo.prediction import predict_followthrough

DATA_DIR = Path(__file__).parent.parent / "data"

# ──────────────────────────────────────────────────────────────────────
# ENTITY REGISTRY: (db_file, display_name, short_name, type)
# ──────────────────────────────────────────────────────────────────────

ENTITIES = [
    ("poc_saydo_trump.db", "Donald Trump", "Trump", "politician"),
    ("poc_saydo_biden.db", "Joe Biden", "Biden", "politician"),
    ("poc_saydo_musk.db", "Elon Musk", "Musk", "CEO"),
    ("poc_saydo_zuckerberg.db", "Mark Zuckerberg", "Zuck", "CEO"),
]


def load_profile(db_name: str, entity_name: str):
    """Load a Say/Do profile from a POC database."""
    db_path = DATA_DIR / db_name
    if not db_path.exists():
        return None, None, None

    store = SQLiteStore(db_path=str(db_path))
    bridge._store_instance = store
    eng_mod._engine_instance = None

    engine = get_saydo_engine()
    profile = engine.get_entity_profile(entity_name)
    contras = engine.get_entity_contradictions(entity_name, min_score=0.0)

    return engine, profile, contras


def load_prediction(db_name: str, entity_name: str, statement: str, category: str):
    """Load a prediction for an entity."""
    db_path = DATA_DIR / db_name
    store = SQLiteStore(db_path=str(db_path))
    bridge._store_instance = store
    eng_mod._engine_instance = None
    return predict_followthrough(entity_name, statement, category)


def bar(value: float, width: int = 25, fill: str = "#", empty: str = ".") -> str:
    filled = int(value * width)
    return f"[{fill * filled}{empty * (width - filled)}]"


def rank_arrow(values: list, idx: int, higher_is_better: bool) -> str:
    """Return rank indicator for a value in a sorted list."""
    sorted_vals = sorted(enumerate(values), key=lambda x: -x[1] if higher_is_better else x[1])
    rank = next(r for r, (i, _) in enumerate(sorted_vals) if i == idx) + 1
    if rank == 1:
        return " <-- BEST"
    elif rank == len(values):
        return " <-- WORST"
    return ""


# ══════════════════════════════════════════════════════════════════════
# LOAD ALL ENTITIES
# ══════════════════════════════════════════════════════════════════════

print()
print("=" * 78)
print("  SAY/DO COMPARATIVE ANALYSIS: 4-WAY")
print("  Contradiction Index Dashboard")
print("=" * 78)

data = {}  # key -> {profile, contradictions, engine, short, db}
available = []

for db_file, display_name, short, etype in ENTITIES:
    eng, prof, contras = load_profile(db_file, display_name)
    if prof is None:
        print(f"  SKIP: {display_name} (run poc_saydo_{short.lower()}.py first)")
        continue
    key = _normalize_entity(display_name)
    data[key] = {
        "profile": prof,
        "contradictions": contras,
        "engine": eng,
        "short": short,
        "display": display_name,
        "db": db_file,
        "type": etype,
    }
    available.append(key)

if len(available) < 2:
    print("\n  Need at least 2 entities to compare. Exiting.")
    sys.exit(1)

print(f"\n  Loaded {len(available)} entities: {', '.join(data[k]['short'] for k in available)}")

# Short names for column headers
shorts = [data[k]["short"] for k in available]
col_w = 10  # column width


def print_header(text: str):
    print()
    w = 14 + col_w * len(available)
    print(f"  {'=' * w}")
    print(f"  {text:^{w}}")
    print(f"  {'=' * w}")


# ══════════════════════════════════════════════════════════════════════
# SECTION 1: LEAGUE TABLE
# ══════════════════════════════════════════════════════════════════════

print_header("LEAGUE TABLE")

metrics = [
    ("Contradiction Score", "contradiction_score", "{:.3f}", False),
    ("Follow-Through Rate", "follow_through_rate", "{:.0%}", True),
    ("Promises Kept", "outcomes_followed", "{}", True),
    ("Promises Broken", "outcomes_broken", "{}", False),
    ("Total Statements", "total_statements", "{}", None),
]

print()
header = f"  {'Metric':<25s}"
for s in shorts:
    header += f"  {s:>{col_w}s}"
header += "  Ranking"
print(header)
print(f"  {'-' * 25}" + f"  {'-' * col_w}" * len(shorts) + f"  {'-' * 20}")

for label, key, fmt, higher_is_better in metrics:
    values = [data[k]["profile"].get(key, 0) for k in available]
    row = f"  {label:<25s}"
    for v in values:
        row += f"  {fmt.format(v):>{col_w}s}"

    if higher_is_better is not None:
        ranked = sorted(zip(shorts, values), key=lambda x: -x[1] if higher_is_better else x[1])
        row += f"  {' > '.join(r[0] for r in ranked)}"
    print(row)

# ══════════════════════════════════════════════════════════════════════
# SECTION 2: VISUAL BARS
# ══════════════════════════════════════════════════════════════════════

print_header("CONTRADICTION SCORE (higher = less trustworthy)")
print()
# Sort by score descending (worst first)
sorted_by_score = sorted(available, key=lambda k: -data[k]["profile"]["contradiction_score"])
for k in sorted_by_score:
    p = data[k]["profile"]
    s = data[k]["short"]
    print(f"  {s:<8s} {bar(p['contradiction_score'])} {p['contradiction_score']:.3f}")

print_header("FOLLOW-THROUGH RATE (higher = more reliable)")
print()
sorted_by_rate = sorted(available, key=lambda k: -data[k]["profile"]["follow_through_rate"])
for k in sorted_by_rate:
    p = data[k]["profile"]
    s = data[k]["short"]
    print(f"  {s:<8s} {bar(p['follow_through_rate'])} {p['follow_through_rate']:.0%}")

# ══════════════════════════════════════════════════════════════════════
# SECTION 3: CATEGORY HEATMAP
# ══════════════════════════════════════════════════════════════════════

print_header("CATEGORY BREAKDOWN PER ENTITY")

for k in available:
    p = data[k]["profile"]
    s = data[k]["short"]
    cats = p.get("categories", {})
    print(f"\n  {s} ({data[k]['display']})")
    print(f"  {'Category':<22s} {'N':>3s} {'Rate':>6s}  Visual")
    print(f"  {'-' * 22} {'-' * 3} {'-' * 6}  {'-' * 17}")

    cat_rates = []
    for cat in sorted(cats.keys()):
        st = cats[cat]
        total = st.get("total", 0)
        f = st.get("followed", 0)
        b = st.get("broken", 0)
        rate = f / max(f + b, 1)
        cat_rates.append((cat, total, rate))

    # Sort by rate descending
    cat_rates.sort(key=lambda x: (-x[2], x[0]))
    for cat, total, rate in cat_rates:
        print(f"  {cat:<22s} {total:>3d} {rate:>5.0%}  {bar(rate, 12)}")

# ══════════════════════════════════════════════════════════════════════
# SECTION 4: TOP 5 CONTRADICTIONS EACH
# ══════════════════════════════════════════════════════════════════════

print_header("TOP 5 CONTRADICTIONS PER ENTITY")

for k in available:
    d = data[k]
    print(f"\n  {d['short']} ({d['display']}):")
    for i, c in enumerate(d["contradictions"][:5], 1):
        summary = c["summary"]
        # Parse: [CONTRADICTION] Name scored X.XX: said '...' but ...
        if "' but " in summary:
            said_start = summary.find("said '")
            but_idx = summary.find("' but ")
            if said_start >= 0 and but_idx > said_start:
                claim = summary[said_start + 6:but_idx]
                # Strip [STATEMENT] prefix
                for prefix in [f"[STATEMENT] {d['display']}: ", "[STATEMENT] "]:
                    if claim.startswith(prefix):
                        claim = claim[len(prefix):]
                        break
                outcome = summary[but_idx + 6:]
                print(f"    {i}. [{c['score']:.3f}] Said: \"{claim[:55]}\"")
                print(f"              Did:  {outcome[:55]}")
                continue
        print(f"    {i}. [{c['score']:.3f}] {summary[:85]}")

# ══════════════════════════════════════════════════════════════════════
# SECTION 5: CROSS-ENTITY PREDICTION FACE-OFF
# ══════════════════════════════════════════════════════════════════════

print_header("PREDICTION FACE-OFF")
print()
print("  Same promise, all entities. Who's most likely to deliver?")

# Universal promises with per-entity category mapping
# Each: (statement, {entity_key: category})
face_offs = [
    ("I will fix the healthcare system", {
        "donald_trump": "healthcare",
        "joe_biden": "healthcare",
        "elon_musk": "product_delivery",
        "mark_zuckerberg": "social_impact",
    }),
    ("I will protect user privacy and data", {
        "donald_trump": "transparency",
        "joe_biden": "governance",
        "elon_musk": "twitter",
        "mark_zuckerberg": "privacy",
    }),
    ("I will create millions of new jobs", {
        "donald_trump": "economy",
        "joe_biden": "economy",
        "elon_musk": "production",
        "mark_zuckerberg": "product_delivery",
    }),
    ("I will deliver transformative technology", {
        "donald_trump": "infrastructure",
        "joe_biden": "infrastructure",
        "elon_musk": "autonomy",
        "mark_zuckerberg": "metaverse",
    }),
    ("I will unite people and reduce division", {
        "donald_trump": "governance",
        "joe_biden": "governance",
        "elon_musk": "twitter",
        "mark_zuckerberg": "social_impact",
    }),
]

print()
header = f"  {'Promise':<40s}"
for s in shorts:
    header += f"  {s:>{col_w}s}"
header += f"  {'Winner':>10s}"
print(header)
print(f"  {'-' * 40}" + f"  {'-' * col_w}" * len(shorts) + f"  {'-' * 10}")

for statement, cat_map in face_offs:
    preds = {}
    for k in available:
        cat = cat_map.get(k, "general")
        pred = load_prediction(data[k]["db"], data[k]["display"], statement, cat)
        preds[k] = pred["probability"]

    row = f"  {statement:<40s}"
    for k in available:
        row += f"  {preds[k]:>{col_w}.1%}"

    winner_k = max(preds, key=preds.get)
    row += f"  {data[winner_k]['short']:>10s}"
    print(row)

# ══════════════════════════════════════════════════════════════════════
# SECTION 6: PATTERN ANALYSIS + ARCHETYPES
# ══════════════════════════════════════════════════════════════════════

print_header("PATTERN ANALYSIS")

for k in available:
    p = data[k]["profile"]
    cats = p.get("categories", {})
    rated = [(c, s.get("followed", 0) / max(s.get("followed", 0) + s.get("broken", 0), 1))
             for c, s in cats.items()
             if s.get("followed", 0) + s.get("broken", 0) >= 1]
    rated.sort(key=lambda x: -x[1])

    best = ", ".join(f"{c} ({r:.0%})" for c, r in rated[:3])
    worst = ", ".join(f"{c} ({r:.0%})" for c, r in rated[-3:])
    zeros = sum(1 for _, r in rated if r == 0.0)

    print(f"\n  {data[k]['short']} ({data[k]['display']})")
    print(f"    Most reliable:    {best}")
    print(f"    Least reliable:   {worst}")
    print(f"    Zero-delivery:    {zeros} categories")

# Archetypes
print_header("ARCHETYPE ANALYSIS")

archetypes = {
    "donald_trump": (
        "The 'Selective Deliverer'",
        "Strong on concrete executive actions (military, trade, judiciary).\n"
        "           Fails on systemic reform (healthcare, immigration, governance, transparency)."
    ),
    "joe_biden": (
        "The 'Legislative Grinder'",
        "Delivers through bipartisan deals and incremental legislation.\n"
        "           Fails when blocked by Congress or courts. Overpromises transformative change,\n"
        "           delivers watered-down versions."
    ),
    "elon_musk": (
        "The 'Timeline Optimist'",
        "Delivers revolutionary engineering milestones (rocket landing, Starlink, EV scale)\n"
        "           but misses nearly every deadline by 2-5 years. Transformative claims\n"
        "           (FSD, Mars, Hyperloop, X super-app) remain undelivered."
    ),
    "mark_zuckerberg": (
        "The 'Pivot Executor'",
        "Delivers through aggressive acquisition and fast-follow copying (Instagram,\n"
        "           WhatsApp, Reels, Stories). Fails on original vision bets (Metaverse, Libra,\n"
        "           Portal). Privacy promises consistently broken."
    ),
}

for k in available:
    if k in archetypes:
        name, desc = archetypes[k]
        print(f"\n    {data[k]['short']}: {name}")
        print(f"           {desc}")

# ══════════════════════════════════════════════════════════════════════
# SECTION 7: FINAL SCORECARD
# ══════════════════════════════════════════════════════════════════════

print_header("FINAL SCORECARD")

scorecard_metrics = [
    ("Contradiction Score", lambda p: p["contradiction_score"], "{:.3f}", False),
    ("Follow-Through Rate", lambda p: p["follow_through_rate"], "{:.0%}", True),
    ("Trustworthiness Index", lambda p: (1 - p["contradiction_score"]) * min(1.0, p["total_statements"] / 30), "{:.3f}", True),
    ("Promises Kept", lambda p: p["outcomes_followed"], "{}", True),
    ("Promises Broken", lambda p: p["outcomes_broken"], "{}", False),
]

print()
header = f"  {'Metric':<25s}"
for s in shorts:
    header += f"  {s:>{col_w}s}"
print(header)
print(f"  {'-' * 25}" + f"  {'-' * col_w}" * len(shorts))

for label, fn, fmt, higher_is_better in scorecard_metrics:
    values = [fn(data[k]["profile"]) for k in available]
    row = f"  {label:<25s}"
    for v in values:
        row += f"  {fmt.format(v):>{col_w}s}"
    print(row)

# Overall ranking by trustworthiness
print()
trust_scores = [(data[k]["short"], (1 - data[k]["profile"]["contradiction_score"]) * min(1.0, data[k]["profile"]["total_statements"] / 30))
                for k in available]
trust_scores.sort(key=lambda x: -x[1])
print("  OVERALL TRUSTWORTHINESS RANKING:")
for rank, (name, score) in enumerate(trust_scores, 1):
    medal = {1: "  [MOST TRUSTWORTHY]", len(trust_scores): "  [LEAST TRUSTWORTHY]"}.get(rank, "")
    print(f"    {rank}. {name:<10s} {score:.3f}{medal}")

# Promise-keeping ranking
print()
kept_scores = [(data[k]["short"], data[k]["profile"]["follow_through_rate"]) for k in available]
kept_scores.sort(key=lambda x: -x[1])
print("  FOLLOW-THROUGH RANKING:")
for rank, (name, rate) in enumerate(kept_scores, 1):
    print(f"    {rank}. {name:<10s} {rate:.0%}")

print()
print("=" * 78)
print("  4-WAY COMPARISON COMPLETE")
print("=" * 78)
print()
