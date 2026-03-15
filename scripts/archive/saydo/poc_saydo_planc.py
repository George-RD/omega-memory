#!/usr/bin/env python3
"""Say/Do POC: PlanC (@TheRealPlanC) Credibility Index.

Populates the Say/Do engine with PlanC's public statements
and their known outcomes, then generates the full credibility profile.

Validation target: ~0.30-0.45 credibility. Bitcoin on-chain analyst with
the Confluence Floor Model (broke in 2022) and Quantile Model. Solid
analytical frameworks but consistent bullish bias, premature bottom-calling,
and model failures when tested in real-time.

All statements sourced from public record (tweets, interviews, model
publications, news coverage).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omega.sqlite_store import SQLiteStore
from omega.saydo.engine import get_saydo_engine, _engine_instance
import omega.saydo.engine as eng_mod
import omega.bridge as bridge

DB_PATH = Path(__file__).parent.parent / "data" / "poc_saydo_planc.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

if DB_PATH.exists():
    DB_PATH.unlink()

store = SQLiteStore(db_path=str(DB_PATH))
bridge._store_instance = store
eng_mod._engine_instance = None

engine = get_saydo_engine()

ENTITY = "PlanC"
ENTITY_TYPE = "person"

DATA = [
    # --- MODEL PREDICTIONS ---
    {
        "statement": (
            "According to the Confluence Floor Model, Bitcoin should not close "
            "the daily candle below $27,688. It has never been broken, so until "
            "it is I feel it is useful"
        ),
        "source": "BeInCrypto, May 2022 (BTC near $28K)",
        "category": "model_prediction",
        "date": "2022-05-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "Bitcoin dropped to $17,600 in June 2022, decisively breaking the $27,688 "
            "floor model on a daily closing basis. The Terra/Luna collapse and subsequent "
            "contagion drove BTC ~37% below the model's floor. This was the model's first "
            "real-time test and it failed."
        ),
        "evidence": "BTC daily close below $18K in June 2022, $27,688 floor broken by 37%",
        "bias": 0.7,
        "source_type": "tech_media",
        "source_url": "https://beincrypto.com/will-bitcoin-btc-hold-the-confluence-floor-model-at-27688/",
    },
    {
        "statement": (
            "The Confluence Floor Model predicted absolute bear market lows in "
            "2011, 2014, 2018 and during the COVID-19 crash in March 2020"
        ),
        "source": "BeInCrypto, March 2022",
        "category": "model_prediction",
        "date": "2022-03-01",
        "outcome_score": 0.6,
        "outcome_detail": (
            "Historical backtesting claims may be accurate for those periods, but the "
            "model failed when tested in real-time in 2022 (BTC broke below $27,688 to "
            "$17,600). Backtested models carry inherent survivor bias and overfitting "
            "risk. The model worked retroactively but failed its first forward test."
        ),
        "evidence": "Historical model fit, but 2022 real-time failure",
        "bias": 0.7,
        "source_type": "tech_media",
    },
    {
        "statement": (
            "The Bitcoin Quantile Model suggests possible trading ranges between "
            "$154,000 median zone and $316,000 historic peak zone, with extended "
            "projections showing potential valuations as high as $769,000 by 2027"
        ),
        "source": "ETHNews and NewsbtC, 2024-2025",
        "category": "model_prediction",
        "date": "2024-06-01",
        "outcome_score": 0.2,
        "outcome_detail": (
            "As of February 2026, Bitcoin is at ~$68,000, well below even the lowest "
            "quantile predictions for this timeframe. The model anticipated BTC would "
            "be in the $154K+ range. While the model is designed for long-term horizons, "
            "current price action significantly diverges from projections."
        ),
        "evidence": "BTC ~$68K vs $154K+ model prediction for this period",
        "bias": 0.6,
        "source_type": "tech_media",
    },

    # --- STRUCTURAL ANALYSIS (THE GOOD) ---
    {
        "statement": (
            "Current market drivers like sustained ETF inflows have shifted the "
            "relevance away from the halving narrative. Bitcoin's increase in "
            "ETF-driven liquidity starkly contrasts its past reliance on halving "
            "cycles for price peaks"
        ),
        "source": "MEXC News, September 2025",
        "category": "market_analysis",
        "date": "2025-09-01",
        "outcome_score": 0.7,
        "outcome_detail": (
            "ETF inflows in 2025 were substantial: daily flows routinely exceeded $500M, "
            "peak days saw $1B+, and record daily inflows of $1.38B followed Trump's "
            "election victory. ETFs did fundamentally alter market structure. However, "
            "Bitcoin still experienced a severe correction from $126K to $60K despite "
            "inflows, suggesting ETFs didn't eliminate volatility as implied."
        ),
        "evidence": "ETF inflow data ($500M+ daily), but $126K->$60K correction persisted",
        "bias": 0.5,
        "source_type": "tech_media",
    },
    {
        "statement": (
            "Anyone who thinks Bitcoin has to peak in Q4 of this year does not "
            "understand statistics or probability. The halving is completely "
            "irrelevant at this point"
        ),
        "source": "Cointelegraph, September 6, 2025",
        "category": "market_analysis",
        "date": "2025-09-06",
        "outcome_score": 0.6,
        "outcome_detail": (
            "Bitcoin reached ATH of $126,210 on October 6, 2025 (early Q4). The "
            "traditional late-Q4 peak pattern didn't play out exactly. However, a "
            "peak DID occur in Q4, just earlier than the typical Dec/Jan window. "
            "PlanC's statistical critique of using 4 data points to predict cycles "
            "was methodologically sound even if the directional call was mixed."
        ),
        "evidence": "BTC ATH $126,210 Oct 6 2025 (Q4), followed by decline",
        "bias": 0.4,
        "source_type": "tech_media",
        "source_url": "https://cointelegraph.com/news/bitcoin-price-top-2025-debate-continues-halving-cycle-analyst",
    },

    # --- BOTTOM-CALLING (THE BAD) ---
    {
        "statement": (
            "Bitcoin's recent decline to approximately $98,000 may mark a "
            "local bottom"
        ),
        "source": "Bitcoin Magazine, late 2025",
        "category": "price_call",
        "date": "2025-12-01",
        "outcome_score": 0.1,
        "outcome_detail": (
            "Bitcoin continued falling from $98K to eventually reach $60K by February "
            "2026, making the $98K bottom call premature by ~39%. Classic premature "
            "bottom-calling pattern."
        ),
        "evidence": "BTC fell from $98K to $60K by Feb 2026",
        "bias": 0.7,
        "source_type": "tech_media",
    },
    {
        "statement": (
            "There's a decent chance this will be the deepest pullback "
            "opportunity this Bitcoin bull run. It seems like the ultimate "
            "low will be between $75,000 and $80,000"
        ),
        "source": "Cointelegraph, early February 2026",
        "category": "price_call",
        "date": "2026-02-01",
        "outcome_score": 0.2,
        "outcome_detail": (
            "Bitcoin briefly touched $75,600 then fell further to ~$60,000 by "
            "February 5, 2026. The $75K-$80K range was NOT the bottom. Second "
            "premature bottom call in quick succession."
        ),
        "evidence": "BTC dropped to ~$60K on Feb 5 2026, below $75K-$80K range",
        "bias": 0.6,
        "source_type": "tech_media",
        "source_url": "https://cointelegraph.com/news/bitcoin-s-price-may-have-seen-deepest-pullback-at-77k-analyst",
    },
    {
        "statement": (
            "Price corrections of 35-40% are historically not unheard of for "
            "a Bitcoin bull run. $75,000 to $80,000 is a 37% to 40% correction"
        ),
        "source": "BeInCrypto, February 2026",
        "category": "market_analysis",
        "date": "2026-02-01",
        "outcome_score": 0.3,
        "outcome_detail": (
            "From the October 2025 ATH of $126,210, a drop to $60,000 represents a "
            "52% correction, exceeding PlanC's 'normal' 35-40% range. This suggests "
            "the correction was more severe than typical bull market behavior."
        ),
        "evidence": "52% correction ($126K->$60K) exceeded 35-40% 'normal' range",
        "bias": 0.7,
        "source_type": "tech_media",
    },

    # --- FORWARD PROJECTIONS ---
    {
        "statement": (
            "MicroStrategy could hold over 1 million Bitcoins by January 1, 2030, "
            "reaching exactly 1,039,965 BTC based on polynomial fitting"
        ),
        "source": "Coinpedia and Binance Square, 2024-2025",
        "category": "projection",
        "date": "2025-01-01",
        "outcome_score": 0.5,
        "outcome_detail": (
            "As of January 2026, MicroStrategy holds 712,647 BTC. At current pace "
            "(~200-250K BTC added per year), reaching 1M by 2030 is mathematically "
            "possible but requires sustained aggressive buying for 4 more years through "
            "varying market conditions. Too early to fully evaluate."
        ),
        "evidence": "MSTR holds 712,647 BTC as of Jan 2026, 4 years to target",
        "bias": 0.5,
        "source_type": "tech_media",
    },

    # --- METHODOLOGICAL CLAIMS ---
    {
        "statement": (
            "The Bitcoin Quantile Model is based on Linear Quantile Regression "
            "which ranks #1 for the lowest risk of overfitting"
        ),
        "source": "X/Twitter @TheRealPlanC, model documentation",
        "category": "methodology",
        "date": "2024-01-01",
        "outcome_score": 0.3,
        "outcome_detail": (
            "While linear quantile regression does reduce overfitting risk compared "
            "to polynomial models, the model's current performance (Bitcoin at $68K vs "
            "predicted $154K+) suggests either incorrect assumptions about market "
            "structure or that reduced overfitting doesn't guarantee accuracy. Good "
            "methodology doesn't automatically produce good predictions."
        ),
        "evidence": "Model divergence: $68K actual vs $154K+ predicted",
        "bias": 0.5,
        "source_type": "social_media",
    },

    # --- META-ANALYSIS ---
    {
        "statement": (
            "Traders who sold BTC may promote bearish forecasts to justify their "
            "exits. Price crash calls are coming from self-serving sellers"
        ),
        "source": "Cointelegraph, late 2025",
        "category": "meta_analysis",
        "date": "2025-11-01",
        "outcome_score": 0.3,
        "outcome_detail": (
            "Bitcoin experienced a significant crash from $126K to $60K in early 2026, "
            "suggesting some bearish analysts were correct regardless of their motivations. "
            "Ironic that PlanC's own bullish stance could be viewed through the same "
            "confirmation bias lens he accuses bears of."
        ),
        "evidence": "BTC crashed $126K->$60K, validating bearish calls PlanC dismissed",
        "bias": 0.6,
        "source_type": "tech_media",
    },

    # --- PATTERN COMPARISON ---
    {
        "statement": (
            "The current downtrend compares to past capitulation episodes like "
            "the 2018 bottom near $3,000, March 2020 crash to $5,100, and the "
            "FTX and Luna collapses"
        ),
        "source": "Cryptonews, February 2026",
        "category": "market_analysis",
        "date": "2026-02-01",
        "outcome_score": 0.4,
        "outcome_detail": (
            "The analytical framework of comparing capitulation events is sound, but "
            "the implied conclusion (that $77K was the bottom like previous events) "
            "was incorrect. BTC fell to $60K. Historical pattern-matching is useful "
            "for context but not predictive on its own."
        ),
        "evidence": "BTC continued to $60K below the $77K 'capitulation' level",
        "bias": 0.6,
        "source_type": "tech_media",
    },
]

# ──────────────────────────────────────────────────────────────────────

print("=" * 70)
print("SAY/DO POC: PlanC (@TheRealPlanC) Credibility Index")
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
    ("Bitcoin will reach $250,000 by 2027", "model_prediction"),
    ("The Quantile Model will accurately predict the next cycle top", "methodology"),
    ("Bitcoin's next major bottom will be accurately identified in advance", "price_call"),
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
    if 0.20 <= cred <= 0.50:
        print(f"  PASS: Credibility score {cred:.3f} in target range [0.20, 0.50]")
    else:
        print(f"  NOTE: Credibility score {cred:.3f} outside target range [0.20, 0.50]")
else:
    print("  WARN: No credibility score computed")

print(f"\n  Contradiction score: {profile['contradiction_score']:.3f}")
print(f"  Total kept: {profile['outcomes_followed']}/{profile['total_statements']}")

print("\n" + "=" * 70)
print("POC COMPLETE")
print("=" * 70)
