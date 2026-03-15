#!/usr/bin/env python3
"""Say/Do POC: Su Zhu (Three Arrows Capital) Credibility Index.

Populates the Say/Do engine with Su Zhu's public statements and their
known outcomes, then generates the full credibility profile.

Validation target: Su Zhu should score BELOW 0.15 credibility.
Co-founder of Three Arrows Capital (3AC), one of crypto's largest hedge
fund collapses ($3.5B+ in losses to creditors).

All statements sourced from public record (tweets, podcasts, interviews,
court documents).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omega.sqlite_store import SQLiteStore
from omega.saydo.engine import get_saydo_engine, _engine_instance
import omega.saydo.engine as eng_mod
import omega.bridge as bridge

DB_PATH = Path(__file__).parent.parent / "data" / "poc_saydo_suzhu.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

if DB_PATH.exists():
    DB_PATH.unlink()

store = SQLiteStore(db_path=str(DB_PATH))
bridge._store_instance = store
eng_mod._engine_instance = None

engine = get_saydo_engine()

ENTITY = "Su Zhu"
ENTITY_TYPE = "person"

DATA = [
    # ─── SUPERCYCLE THESIS ───
    {
        "statement": (
            "We are in a crypto supercycle. This is not a normal bull market. "
            "The structural demand from institutions means we won't see an 80% "
            "drawdown like previous cycles"
        ),
        "source": "Multiple podcast appearances and tweets, 2021",
        "category": "market_prediction",
        "date": "2021-03-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "Bitcoin fell from $69K (Nov 2021) to $15.5K (Nov 2022), a 77% drawdown. "
            "ETH fell from $4.8K to $880, an 82% drawdown. The 'supercycle' thesis was "
            "completely wrong. The drawdown was nearly identical to previous cycles, "
            "exactly what Su Zhu said wouldn't happen."
        ),
        "evidence": "BTC/ETH price data 2021-2022",
        "bias": 0.5,  # Positioned long, talked his book
        "source_type": "podcast",
    },
    {
        "statement": (
            "Bitcoin will reach $2.5 million per coin in this supercycle. "
            "The macro setup is unprecedented"
        ),
        "source": "Podcast appearances and social media, late 2021",
        "category": "market_prediction",
        "date": "2021-10-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "Bitcoin peaked at ~$69K in November 2021 and crashed to $15.5K by November "
            "2022. The $2.5M prediction was off by approximately 36x from the actual peak "
            "and over 160x from the subsequent low. One of the most wrong price predictions "
            "in crypto history."
        ),
        "evidence": "Bitcoin price data, 3AC portfolio losses",
        "bias": 0.6,
        "deadline": "2022-12-31",
        "source_type": "podcast",
    },
    {
        "statement": (
            "The supercycle thesis doesn't require constant up-only. We're talking about "
            "a structural shift where crypto becomes a permanent macro asset class with "
            "multi-trillion dollar sustained market cap"
        ),
        "source": "Uncommon Core podcast and Twitter Spaces, 2021",
        "category": "market_prediction",
        "date": "2021-06-01",
        "outcome_score": 0.2,
        "outcome_detail": (
            "Crypto did continue growing as an asset class long-term, and institutional "
            "adoption continued (Bitcoin ETFs approved Jan 2024). However, the 2022 crash "
            "was devastating, 3AC itself became one of the biggest casualties, and the "
            "'no 80% drawdown' prediction was definitively wrong. Su Zhu's own fund didn't "
            "survive the cycle he predicted would be different."
        ),
        "evidence": "Crypto market data, 3AC bankruptcy, Bitcoin ETF approvals",
        "bias": 0.5,
        "source_type": "podcast",
    },

    # ─── LUNA/UST EXPOSURE ───
    {
        "statement": (
            "We are very bullish on LUNA and UST. The Terra ecosystem represents one of "
            "the most innovative approaches to decentralized money. We have significant "
            "exposure"
        ),
        "source": "Multiple public statements and on-chain evidence, 2021-2022",
        "category": "investment_thesis",
        "date": "2021-12-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "3AC had approximately $559M in LUNA/UST exposure (per bankruptcy filings). "
            "LUNA crashed from ~$119 to near zero in May 2022. This single position "
            "accounted for a massive portion of 3AC's losses and was a primary catalyst "
            "for the fund's collapse."
        ),
        "evidence": "3AC bankruptcy filings, on-chain analysis of 3AC wallets",
        "bias": 0.5,
        "source_type": "social_media",
    },

    # ─── GBTC ARBITRAGE ───
    {
        "statement": (
            "The GBTC premium trade is one of the best risk-adjusted opportunities "
            "in crypto. Buying GBTC at a discount to NAV is a structural trade that "
            "will converge"
        ),
        "source": "Public statements and investor communications, 2021",
        "category": "investment_thesis",
        "date": "2021-01-01",
        "outcome_score": 0.1,
        "outcome_detail": (
            "3AC accumulated a massive GBTC position (~$2.3B at peak). The premium "
            "flipped to a persistent discount in Feb 2021, falling to -50% by Dec 2022. "
            "3AC was locked into shares with 6-month redemption periods while the discount "
            "widened. The trade eventually converged when Bitcoin ETFs were approved in "
            "Jan 2024, but 3AC was long bankrupt by then. The trade thesis was right "
            "long-term but 3AC was liquidated before it played out."
        ),
        "evidence": "GBTC NAV premium/discount data, 3AC GBTC holdings disclosures",
        "bias": 0.5,
        "source_type": "official",
    },

    # ─── RISK MANAGEMENT CLAIMS ───
    {
        "statement": (
            "We run a sophisticated operation. Three Arrows Capital has strong risk "
            "management and portfolio construction. We're not just levered long"
        ),
        "source": "Multiple podcast and interview appearances, 2021",
        "category": "risk_management",
        "date": "2021-06-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "3AC was, in fact, massively levered long with concentrated positions. "
            "They borrowed from over 20 lenders including BlockFi, Voyager, Genesis, "
            "and Celsius with no risk hedging. When LUNA collapsed and BTC dropped, "
            "3AC couldn't meet margin calls. Liquidators found almost no hedges. "
            "Total creditor claims exceeded $3.5 billion."
        ),
        "evidence": "3AC bankruptcy liquidator report, creditor claims",
        "bias": 0.5,
        "source_type": "podcast",
    },
    {
        "statement": (
            "We've been through multiple cycles. We survived 2018. We know how to "
            "manage drawdowns. Our portfolio is constructed to weather volatility"
        ),
        "source": "Interviews and investor communications, 2021",
        "category": "risk_management",
        "date": "2021-09-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "3AC did not survive the 2022 drawdown. Unlike 2018 where they were smaller "
            "and less leveraged, in 2022 they had massive concentrated bets with extensive "
            "borrowing. The fund went from ~$10B AUM to insolvency in weeks. Their "
            "'experience' with cycles did not prevent catastrophic failure."
        ),
        "evidence": "3AC bankruptcy filing July 2022, creditor losses",
        "bias": 0.5,
        "source_type": "interview",
    },

    # ─── "WE'RE FINE" / COMMUNICATION FAILURES ───
    {
        "statement": (
            "We are in the process of communicating with relevant parties and fully "
            "committed to working this out"
        ),
        "source": "Tweet @zaborskiy (Su Zhu's Twitter), June 15, 2022",
        "category": "transparency",
        "date": "2022-06-15",
        "outcome_score": 0.0,
        "outcome_detail": (
            "Su Zhu and Kyle Davies went silent after this tweet. Lenders reported "
            "that 3AC stopped answering calls and emails. Within weeks, 3AC filed for "
            "Chapter 15 bankruptcy in New York. The founders fled to Dubai. Creditors "
            "described a complete communication blackout."
        ),
        "evidence": "Creditor statements, bankruptcy filing timeline",
        "bias": 0.6,
        "source_type": "social_media",
    },

    # ─── POST-COLLAPSE BEHAVIOR ───
    {
        "statement": (
            "We had always intended to cooperate with the liquidation process and "
            "help creditors recover their funds"
        ),
        "source": "Statements through lawyers, mid-2022",
        "category": "legal",
        "date": "2022-07-15",
        "outcome_score": 0.0,
        "outcome_detail": (
            "Su Zhu and Kyle Davies were found in contempt of court for failing to "
            "cooperate with liquidators. They initially fled to Dubai and refused to "
            "appear. A Singapore court issued arrest warrants. Su Zhu was arrested at "
            "Changi Airport in September 2023 while attempting to leave Singapore "
            "and sentenced to 4 months in prison for contempt."
        ),
        "evidence": "Singapore court records, arrest September 2023",
        "bias": 0.6,
        "source_type": "official",
    },
    {
        "statement": (
            "We're concerned about the treatment of creditors in the bankruptcy process. "
            "We want to ensure fair outcomes for all stakeholders"
        ),
        "source": "Public statements through representatives, 2022",
        "category": "transparency",
        "date": "2022-08-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "While claiming concern for creditors, Su Zhu and Kyle Davies were living "
            "lavishly in Dubai. Reports emerged of luxury properties and yachts. They "
            "launched a new venture (OPNX) while creditors remained unpaid. The stated "
            "concern for creditors was contradicted by their actions."
        ),
        "evidence": "Creditor committee statements, media reports of Dubai lifestyle",
        "bias": 0.6,
        "source_type": "official",
    },

    # ─── OPNX EXCHANGE ───
    {
        "statement": (
            "OPNX (Open Exchange) will create a marketplace for bankrupt crypto claims. "
            "This is about bringing transparency and liquidity to the bankruptcy process "
            "and helping creditors recover value faster"
        ),
        "source": "OPNX launch announcements, January-February 2023",
        "category": "business",
        "date": "2023-01-01",
        "outcome_score": 0.05,
        "outcome_detail": (
            "OPNX launched to widespread criticism for its tone-deafness: the founders "
            "who caused billions in creditor losses were now trying to profit from "
            "trading those same claims. The exchange achieved minimal volume (~$600/day "
            "at one point). Singapore's MAS warned it was unregulated. OPNX was shut down "
            "by February 2024 after failing to gain traction."
        ),
        "evidence": "OPNX trading volume data, MAS warnings, exchange shutdown",
        "bias": 0.6,
        "source_type": "official",
    },

    # ─── EARLY LEGITIMATE CALLS (for balance) ───
    {
        "statement": (
            "Ethereum is significantly undervalued relative to Bitcoin. The ETH/BTC "
            "ratio will increase substantially as DeFi and smart contract adoption grows"
        ),
        "source": "Multiple tweets and podcast appearances, 2020-early 2021",
        "category": "market_prediction",
        "date": "2020-07-01",
        "outcome_score": 0.7,
        "outcome_detail": (
            "This was one of Su Zhu's correct calls. ETH/BTC rose from ~0.025 in July "
            "2020 to ~0.085 by November 2021 (240% gain in ratio terms). ETH went from "
            "~$230 to ~$4,800. DeFi adoption did drive massive ETH demand. However, the "
            "ratio subsequently crashed back during the bear market."
        ),
        "evidence": "ETH/BTC price data 2020-2021",
        "bias": 0.4,
        "source_type": "social_media",
    },
    {
        "statement": (
            "DeFi is going to be much bigger than people think. Decentralized finance "
            "will reach hundreds of billions in TVL within 2 years"
        ),
        "source": "Uncommon Core podcast and public statements, 2020",
        "category": "investment_thesis",
        "date": "2020-08-01",
        "outcome_score": 0.8,
        "outcome_detail": (
            "DeFi TVL grew from ~$8B in August 2020 to over $250B by November 2021, "
            "validating the directional thesis. Su Zhu was genuinely early and correct "
            "on the DeFi growth trajectory. However, TVL subsequently crashed to ~$40B "
            "in the bear market, and the 'permanently higher plateau' framing was wrong."
        ),
        "evidence": "DeFi Llama TVL data",
        "bias": 0.4,
        "deadline": "2022-08-01",
        "source_type": "podcast",
    },

    # ─── LEVERAGE DENIAL ───
    {
        "statement": (
            "The rumors about our leverage are greatly exaggerated. We manage our "
            "positions conservatively relative to our equity base"
        ),
        "source": "Public and private communications to lenders, early 2022",
        "category": "risk_management",
        "date": "2022-02-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "3AC's leverage was not exaggerated; it was understated. The fund borrowed "
            "from over 20 counterparties, often without disclosing total borrowings to "
            "any single lender. Total liabilities exceeded $3.5B against rapidly "
            "declining assets. Multiple lenders reported that 3AC misrepresented its "
            "financial position to secure loans."
        ),
        "evidence": "Bankruptcy creditor claims, lender testimony",
        "bias": 0.6,
        "source_type": "official",
    },
]

# ──────────────────────────────────────────────────────────────────────

print("=" * 70)
print("SAY/DO POC: Su Zhu (Three Arrows Capital) Credibility Index")
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
        kwargs["followed_through"] = d.get("followed_through", False)

    if "evidence_url" in d:
        kwargs["evidence_url"] = d["evidence_url"]

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
if "brier_score" in profile:
    print(f"  Brier Score:         {profile['brier_score']:.4f}")
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
print("\nPHASE 4: Top Contradictions")
print("=" * 70)
contradictions = engine.get_entity_contradictions(ENTITY, min_score=0.0)
for i, c in enumerate(contradictions[:10], 1):
    print(f"  {i}. [score={c['score']:.3f}] {c['summary'][:100]}")

# Phase 5: Predictions
print("\nPHASE 5: Follow-Through Predictions (hypothetical claims)")
print("=" * 70)
from omega.saydo.prediction import predict_followthrough

test_statements = [
    ("I will cooperate fully with the liquidation process", "legal"),
    ("My next venture will prioritize transparency and risk management", "business"),
    ("The crypto market will enter another supercycle", "market_prediction"),
]

for stmt, cat in test_statements:
    pred = predict_followthrough(ENTITY, stmt, cat)
    ci = pred.get("confidence_interval", {})
    print(f"\n  Statement: \"{stmt}\"")
    print(f"  Category:    {cat}")
    print(f"  Probability: {pred['probability']:.1%}")
    print(f"  Confidence:  {pred['confidence']:.1%}")
    if ci:
        print(f"  95% CI:      [{ci.get('lower', 0):.1%}, {ci.get('upper', 1):.1%}]")
    for r in pred["reasoning"]:
        print(f"    - {r}")

# Phase 6: Validation check
print("\n" + "=" * 70)
print("VALIDATION CHECK")
print("=" * 70)
cred = profile.get("credibility_score", None)
if cred is not None:
    if cred < 0.15:
        print(f"  PASS: Credibility score {cred:.3f} < 0.15 threshold")
    else:
        print(f"  FAIL: Credibility score {cred:.3f} >= 0.15 threshold")
        print(f"  The credibility system may need tuning.")
else:
    print("  WARN: No credibility score computed")

ftr = profile.get("follow_through_rate", 1.0)
if ftr < 0.25:
    print(f"  PASS: Follow-through rate {ftr:.0%} < 25%")
else:
    print(f"  WARN: Follow-through rate {ftr:.0%} >= 25%")

print(f"\n  Contradiction score: {profile['contradiction_score']:.3f}")
print(f"  Total broken: {profile['outcomes_broken']}/{profile['total_statements']}")

print("\n" + "=" * 70)
print("POC COMPLETE")
print("=" * 70)
