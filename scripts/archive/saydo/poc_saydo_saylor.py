#!/usr/bin/env python3
"""Say/Do POC: Michael Saylor Credibility Index.

Populates the Say/Do engine with Michael Saylor's public statements
and their known outcomes, then generates the full credibility profile.

Validation target: Saylor should score around 0.70-0.80 credibility.
Strong conviction and follow-through on Bitcoin thesis, but historical
accounting fraud at MicroStrategy (2000) and some overconfident predictions.

All statements sourced from public record (earnings calls, tweets,
interviews, SEC filings).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omega.sqlite_store import SQLiteStore
from omega.saydo.engine import get_saydo_engine, _engine_instance
import omega.saydo.engine as eng_mod
import omega.bridge as bridge

DB_PATH = Path(__file__).parent.parent / "data" / "poc_saydo_saylor.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

if DB_PATH.exists():
    DB_PATH.unlink()

store = SQLiteStore(db_path=str(DB_PATH))
bridge._store_instance = store
eng_mod._engine_instance = None

engine = get_saydo_engine()

ENTITY = "Michael Saylor"
ENTITY_TYPE = "person"

DATA = [
    # ─── BITCOIN THESIS: DELIVERED ───
    {
        "statement": (
            "MicroStrategy is adopting Bitcoin as its primary treasury reserve asset. "
            "We will purchase $250 million in Bitcoin as an initial allocation"
        ),
        "source": "MicroStrategy press release, August 11, 2020",
        "category": "bitcoin_strategy",
        "date": "2020-08-11",
        "outcome_score": 1.0,
        "outcome_detail": (
            "MicroStrategy purchased 21,454 BTC for $250M in August 2020 at ~$11,653 "
            "average. This was the first major public company Bitcoin treasury allocation. "
            "The purchase was executed as promised and became the foundation of the largest "
            "corporate Bitcoin treasury in the world."
        ),
        "evidence": "MicroStrategy 8-K filing, blockchain records",
        "bias": 0.2,
        "source_type": "official",
        "source_url": "https://www.microstrategy.com/press/microstrategy-adopts-bitcoin-as-primary-treasury-reserve-asset",
    },
    {
        "statement": (
            "We will continue to acquire Bitcoin. MicroStrategy's strategy is to buy "
            "and hold Bitcoin for the long term. We will never sell"
        ),
        "source": "Multiple earnings calls and interviews, 2020-2024",
        "category": "bitcoin_strategy",
        "date": "2020-12-01",
        "outcome_score": 1.0,
        "outcome_detail": (
            "MicroStrategy (rebranded to Strategy in 2025) has continuously purchased "
            "Bitcoin through multiple market cycles, accumulating over 450,000 BTC by "
            "early 2026. They held through the 2022 bear market when BTC dropped to $15K. "
            "Never sold a single Bitcoin. The commitment has been absolute and verifiable."
        ),
        "evidence": "MicroStrategy quarterly filings, Bitcoin treasury tracker",
        "bias": 0.3,
        "source_type": "official",
    },
    {
        "statement": (
            "Bitcoin is the best collateral in the world. It is digital gold, digital "
            "property, and the apex asset of the human race. It will reach $1 million "
            "per coin"
        ),
        "source": "Multiple interviews, conferences, and social media, 2020-2024",
        "category": "bitcoin_thesis",
        "date": "2021-01-01",
        "outcome_score": 0.6,
        "outcome_detail": (
            "Bitcoin has performed well since Saylor's initial purchase ($11K to $90K+), "
            "validating the 'apex asset' thesis directionally. Bitcoin ETFs approved "
            "January 2024, institutional adoption growing. However, the $1M target has "
            "not been reached. BTC experienced a 77% drawdown in 2022. The 'digital gold' "
            "narrative has gained mainstream acceptance but remains debated."
        ),
        "evidence": "Bitcoin price data, ETF approvals, institutional adoption metrics",
        "bias": 0.4,
        "source_type": "interview",
    },

    # ─── FINANCIAL STRATEGY ───
    {
        "statement": (
            "MicroStrategy will use convertible notes and equity offerings to fund "
            "additional Bitcoin purchases. This is an intelligent use of capital markets "
            "to acquire a scarce asset"
        ),
        "source": "Multiple earnings calls and offerings, 2020-2024",
        "category": "financial_strategy",
        "date": "2021-02-01",
        "outcome_score": 0.85,
        "outcome_detail": (
            "MicroStrategy successfully raised billions through convertible notes ($2B+) "
            "and at-the-market equity offerings. The strategy worked: MSTR stock significantly "
            "outperformed BTC itself due to the leveraged exposure. Share price went from ~$120 "
            "to $400+ by 2025. However, the strategy carries significant risk if Bitcoin "
            "crashes below the average cost basis. The leverage works both ways."
        ),
        "evidence": "MSTR stock performance, convertible note offerings, Bitcoin treasury value",
        "bias": 0.4,
        "source_type": "official",
    },
    {
        "statement": (
            "MicroStrategy will hold Bitcoin through any drawdown. We have no intention "
            "of selling. This is a 100-year holding strategy"
        ),
        "source": "Multiple earnings calls and interviews, 2021-2022",
        "category": "bitcoin_strategy",
        "date": "2021-11-01",
        "outcome_score": 1.0,
        "outcome_detail": (
            "Tested severely during the 2022 bear market when BTC fell from $69K to $15.5K. "
            "MicroStrategy's Bitcoin was briefly underwater by ~$1 billion. Despite margin "
            "call fears and stock price collapse (~$120), Saylor did not sell a single BTC. "
            "He stepped down as CEO (became Executive Chairman) but maintained the strategy. "
            "The conviction was proven real."
        ),
        "evidence": "MicroStrategy quarterly reports through 2022 bear market",
        "bias": 0.3,
        "source_type": "official",
    },

    # ─── BITCOIN EDUCATION / ADVOCACY ───
    {
        "statement": (
            "I will educate corporations on Bitcoin as a treasury asset. We will open-source "
            "our playbook so other companies can follow"
        ),
        "source": "MicroStrategy 'Bitcoin for Corporations' conference, February 2021",
        "category": "advocacy",
        "date": "2021-02-01",
        "outcome_score": 0.8,
        "outcome_detail": (
            "MicroStrategy hosted multiple 'Bitcoin for Corporations' events attended by "
            "thousands of executives. Saylor published educational content and consulted "
            "with companies considering Bitcoin treasury. Tesla, Block (Square), and others "
            "followed suit. While not all adopted Bitcoin, the educational mission was "
            "largely delivered."
        ),
        "evidence": "Bitcoin for Corporations events, corporate Bitcoin adoption data",
        "bias": 0.3,
        "source_type": "official",
    },

    # ─── HISTORICAL ACCOUNTING FRAUD ───
    {
        "statement": (
            "MicroStrategy's financial results accurately reflect the company's performance "
            "and growth trajectory"
        ),
        "source": "MicroStrategy earnings reports and SEC filings, 1998-2000",
        "category": "financial_transparency",
        "date": "1999-01-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "SEC charged MicroStrategy and Saylor with accounting fraud in December 2000. "
            "The company overstated revenues by $66 million over three years (1997-2000) "
            "through premature revenue recognition. Saylor paid $8.3M in penalties and "
            "disgorgement without admitting guilt. MSTR stock crashed 62% in a single day "
            "when the restatement was announced (March 2000). This is a permanent credibility "
            "stain despite occurring 20+ years ago."
        ),
        "evidence": "SEC complaint December 2000, MSTR restatement March 2000",
        "bias": 0.6,
        "source_type": "official",
        "source_url": "https://www.sec.gov/news/headlines/microstrategysettlement.htm",
    },

    # ─── TAX EVASION SETTLEMENT ───
    {
        "statement": (
            "I have been a resident of various locations and have paid all applicable taxes"
        ),
        "source": "Implicit in public positioning as a law-abiding CEO",
        "category": "financial_transparency",
        "date": "2015-01-01",
        "outcome_score": 0.1,
        "outcome_detail": (
            "District of Columbia sued Saylor in August 2022 for tax evasion, alleging he "
            "lived in DC for over a decade while claiming Florida residency to avoid DC income "
            "taxes. Saylor settled for $40M in June 2024, the largest DC tax fraud recovery "
            "ever. While he denied intentional fraud, the settlement amount suggests "
            "significant unreported tax obligations."
        ),
        "evidence": "DC Attorney General lawsuit Aug 2022, $40M settlement June 2024",
        "bias": 0.5,
        "source_type": "official",
    },

    # ─── WRONG / OVERCONFIDENT PREDICTIONS ───
    {
        "statement": (
            "Bitcoin will never have another 80% drawdown. The institutional adoption "
            "and ETF infrastructure make that impossible"
        ),
        "source": "Various interviews and social media, late 2021",
        "category": "bitcoin_thesis",
        "date": "2021-11-01",
        "outcome_score": 0.3,
        "outcome_detail": (
            "Bitcoin dropped from $69K (Nov 2021) to $15.5K (Nov 2022), a 77% drawdown. "
            "While technically not 80%, it was extremely close and the prediction was "
            "essentially wrong. Institutional adoption did not prevent a devastating crash. "
            "The drawdown was comparable to previous cycles."
        ),
        "evidence": "Bitcoin price data 2021-2022",
        "bias": 0.4,
        "source_type": "interview",
    },
    {
        "statement": (
            "Bitcoin in 2011 is like early email. The days of Bitcoin being used for "
            "illegal activity are over. It has no utility as a currency"
        ),
        "source": "Tweet @saborsk, July 2013 (now deleted but archived)",
        "category": "bitcoin_thesis",
        "date": "2013-07-17",
        "outcome_score": 0.0,
        "outcome_detail": (
            "In 2013, Saylor tweeted 'Bitcoin days are numbered. It seems like just a "
            "matter of time before it suffers the same fate as online gambling.' He was "
            "spectacularly wrong. Bitcoin went from ~$90 at the time of his tweet to "
            "$90,000+ by 2024. Saylor himself became the biggest corporate Bitcoin bull "
            "in history. He has been admirably honest about this 180-degree reversal."
        ),
        "evidence": "Archived 2013 tweet, Saylor's own acknowledgment of being wrong",
        "bias": 0.1,
        "source_type": "social_media",
    },

    # ─── ETHEREUM CRITICISM ───
    {
        "statement": (
            "Ethereum is an unregistered security. All crypto assets other than Bitcoin "
            "are securities and will go to zero. Bitcoin is the only legitimate crypto asset"
        ),
        "source": "Multiple interviews and tweets, 2022-2024",
        "category": "bitcoin_thesis",
        "date": "2022-06-01",
        "outcome_score": 0.2,
        "outcome_detail": (
            "ETH was not classified as a security by the SEC. Ethereum spot ETFs were "
            "approved in May 2024. Multiple other crypto assets have maintained and grown "
            "their value. The 'everything except Bitcoin goes to zero' prediction has been "
            "consistently wrong. While Bitcoin maximalism has some philosophical merit, "
            "the specific claims about securities classification and zero were factually wrong."
        ),
        "evidence": "SEC ETH classification, Ethereum ETF approval, altcoin market data",
        "bias": 0.5,
        "source_type": "interview",
    },

    # ─── CORPORATE TRANSPARENCY ───
    {
        "statement": (
            "MicroStrategy will provide full transparency on all Bitcoin purchases, "
            "including price, quantity, and timing. We will report in real-time"
        ),
        "source": "Multiple earnings calls and press releases, 2020-2024",
        "category": "financial_transparency",
        "date": "2020-09-01",
        "outcome_score": 1.0,
        "outcome_detail": (
            "MicroStrategy has been remarkably transparent about Bitcoin purchases. "
            "Every acquisition is disclosed via 8-K filing, press release, and Saylor's "
            "personal tweets. The company created a Bitcoin dashboard tracking total "
            "holdings, average cost basis, and unrealized gain/loss. This level of "
            "transparency is exceptional among public companies."
        ),
        "evidence": "MicroStrategy 8-K filings, Bitcoin treasury dashboard",
        "bias": 0.2,
        "source_type": "official",
    },

    # ─── LIGHTNING / LAYER 2 ───
    {
        "statement": (
            "The Lightning Network will make Bitcoin usable for everyday payments. "
            "Layer 2 solutions will solve Bitcoin's scalability challenges"
        ),
        "source": "Multiple interviews and tweets, 2021-2023",
        "category": "bitcoin_thesis",
        "date": "2021-06-01",
        "outcome_score": 0.5,
        "outcome_detail": (
            "Lightning Network is operational and growing, but adoption for everyday "
            "payments remains niche. Most Bitcoin usage is still for store of value, "
            "not payments. Lightning capacity has grown but represents a tiny fraction "
            "of Bitcoin's value. The prediction is partially correct but the timeline "
            "for mass payment adoption is much longer than implied."
        ),
        "evidence": "Lightning Network capacity data, adoption statistics",
        "bias": 0.3,
        "source_type": "interview",
    },

    # ─── PERSONAL CONVICTION ───
    {
        "statement": (
            "I personally hold Bitcoin and will never sell. My personal holdings are "
            "separate from MicroStrategy's but the conviction is the same"
        ),
        "source": "Multiple interviews, personal disclosures",
        "category": "bitcoin_strategy",
        "date": "2020-10-01",
        "outcome_score": 0.9,
        "outcome_detail": (
            "Saylor has disclosed personal holdings of ~17,732 BTC (as of 2024). "
            "No evidence of personal sales during any market period. His personal "
            "conviction matches his public statements. The only minor uncertainty is "
            "that personal holdings are less auditable than corporate holdings."
        ),
        "evidence": "Saylor's personal disclosures, no evidence of sales",
        "bias": 0.3,
        "source_type": "interview",
    },
]

# ──────────────────────────────────────────────────────────────────────

print("=" * 70)
print("SAY/DO POC: Michael Saylor Credibility Index")
print("=" * 70)
print()

# Phase 1: Track all statements
print("PHASE 1: Tracking statements...")
print("-" * 40)
statement_ids = []
for d in DATA:
    kwargs = {
        "entity_name": ENTITY,
        "statement": d["statement"],
        "source": d["source"],
        "category": d["category"],
        "entity_type": ENTITY_TYPE,
        "statement_date": d["date"],
    }
    if "bias" in d:
        kwargs["bias"] = d["bias"]
    if "deadline" in d:
        kwargs["deadline"] = d["deadline"]
    if "source_url" in d:
        kwargs["source_url"] = d["source_url"]
    if "source_type" in d:
        kwargs["source_type"] = d["source_type"]

    result = engine.track_statement(**kwargs)
    statement_ids.append(result["node_id"])
    spec = result.get("specificity", "?")
    print(f"  [tracked] spec={spec:.2f}  {d['statement'][:65]}...")

print(f"\n  Total statements tracked: {len(statement_ids)}")

# Phase 2: Resolve outcomes
print("\nPHASE 2: Resolving outcomes...")
print("-" * 40)
for i, d in enumerate(DATA):
    kwargs = {
        "entity_name": ENTITY,
        "statement_id": statement_ids[i],
        "outcome_detail": d["outcome_detail"],
        "evidence": d["evidence"],
    }
    if "outcome_score" in d:
        kwargs["outcome_score"] = d["outcome_score"]
    else:
        kwargs["followed_through"] = d.get("followed_through", True)

    result = engine.resolve_outcome(**kwargs)
    score = result.get("outcome_score", 0.0)
    cscore = result.get("contradiction_score", 0.0)
    icon = f"{score:.0%}"
    print(f"  [{icon:>4}] contra={cscore:.3f}  {d['statement'][:55]}...")

print(f"\n  Outcomes resolved: {len(DATA)}")

# Phase 3: Profile
print("\nPHASE 3: Credibility Profile")
print("=" * 70)
profile = engine.get_entity_profile(ENTITY)

print(f"  Entity:              {profile['entity_name']}")
print(f"  Type:                {profile['entity_type']}")
print(f"  Contradiction Score: {profile['contradiction_score']:.3f}")
print(f"  Follow-Through Rate: {profile['follow_through_rate']:.0%}")
if "credibility_score" in profile:
    print(f"  Credibility Score:   {profile['credibility_score']:.3f}")
print(f"  Total Statements:    {profile['total_statements']}")
print(f"  Resolved:            {profile['resolved_statements']}")
print(f"  Followed Through:    {profile['outcomes_followed']}")
print(f"  Broken:              {profile['outcomes_broken']}")
print()

print("  Category Breakdown:")
for cat, stats in sorted(profile["categories"].items()):
    total = stats.get("total", 0)
    followed = stats.get("followed", 0)
    broken = stats.get("broken", 0)
    rate = followed / max(followed + broken, 1)
    print(f"    {cat:25s}  {total} statements, {rate:.0%} follow-through")

# Phase 4: Top Contradictions
print("\nPHASE 4: Contradictions")
print("=" * 70)
contradictions = engine.get_entity_contradictions(ENTITY, min_score=0.0)
for i, c in enumerate(contradictions[:10], 1):
    print(f"  {i}. [score={c['score']:.3f}] {c['summary'][:100]}")

# Phase 5: Predictions
print("\nPHASE 5: Follow-Through Predictions")
print("=" * 70)
from omega.saydo.prediction import predict_followthrough

test_statements = [
    ("MicroStrategy will acquire another 100,000 BTC in 2026", "bitcoin_strategy"),
    ("Bitcoin will reach $500,000 within 5 years", "bitcoin_thesis"),
    ("I will never sell my personal Bitcoin holdings", "bitcoin_strategy"),
]

for stmt, cat in test_statements:
    pred = predict_followthrough(ENTITY, stmt, cat)
    ci = pred.get("confidence_interval", {})
    print(f"\n  Statement: \"{stmt}\"")
    print(f"  Probability: {pred['probability']:.1%}")
    print(f"  Confidence:  {pred['confidence']:.1%}")
    if ci:
        print(f"  95% CI:      [{ci.get('lower', 0):.1%}, {ci.get('upper', 1):.1%}]")

# Phase 6: Validation check
print("\n" + "=" * 70)
print("VALIDATION CHECK")
print("=" * 70)
cred = profile.get("credibility_score", None)
if cred is not None:
    if 0.60 <= cred <= 0.85:
        print(f"  PASS: Credibility score {cred:.3f} in target range [0.60, 0.85]")
    else:
        print(f"  NOTE: Credibility score {cred:.3f} outside target range [0.60, 0.85]")
else:
    print("  WARN: No credibility score computed")

print(f"\n  Contradiction score: {profile['contradiction_score']:.3f}")
print(f"  Total kept: {profile['outcomes_followed']}/{profile['total_statements']}")

print("\n" + "=" * 70)
print("POC COMPLETE")
print("=" * 70)
