#!/usr/bin/env python3
"""Say/Do POC: Max Keiser Credibility Index.

Populates the Say/Do engine with Max Keiser's public statements
and their known outcomes, then generates the full credibility profile.

Validation target: ~0.35-0.50 credibility. Early Bitcoin visionary who
bought at $1 (2011), but serial failed predictions with specific timelines,
MaxCoin/StartCoin disasters, El Salvador advisor during adoption collapse,
and volcano bonds that never launched.

All statements sourced from public record (Keiser Report, tweets,
interviews, press coverage).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omega.sqlite_store import SQLiteStore
from omega.saydo.engine import get_saydo_engine, _engine_instance
import omega.saydo.engine as eng_mod
import omega.bridge as bridge

DB_PATH = Path(__file__).parent.parent / "data" / "poc_saydo_keiser.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

if DB_PATH.exists():
    DB_PATH.unlink()

store = SQLiteStore(db_path=str(DB_PATH))
bridge._store_instance = store
eng_mod._engine_instance = None

engine = get_saydo_engine()

ENTITY = "Max Keiser"
ENTITY_TYPE = "person"

DATA = [
    # --- EARLY BITCOIN VISION (THE GOOD) ---
    {
        "statement": (
            "Bitcoin could reach between $100,000 and $1 million per Bitcoin. "
            "I am buying Bitcoin at $1 and recommend everyone do the same"
        ),
        "source": "Keiser Report on RT, 2011 (BTC at ~$1)",
        "category": "bitcoin_prediction",
        "date": "2011-01-01",
        "outcome_score": 0.85,
        "outcome_detail": (
            "Bitcoin reached $100,000 on December 5, 2024 (14 years later), hitting "
            "$103,679. The lower bound of his prediction was achieved. The upper bound "
            "($1M) has not been reached as of February 2026. Keiser was one of the "
            "earliest public advocates recommending Bitcoin at $1, which makes this one "
            "of the most prescient calls in crypto history, even if the timeline was "
            "much longer than implied."
        ),
        "evidence": "BTC price history, Keiser Report archives, $100K milestone Dec 5 2024",
        "bias": 0.5,
        "source_type": "broadcast",
    },
    {
        "statement": (
            "Bitcoin Cash is outright fraud, plagiarizing Bitcoin's brand name. "
            "BCH will fail and Bitcoin will remain the dominant chain"
        ),
        "source": "CNBC and Bitcoinist, December 2017",
        "category": "altcoin_critique",
        "date": "2017-12-01",
        "outcome_score": 0.80,
        "outcome_detail": (
            "Bitcoin Cash declined from a high of ~$4,000 (Dec 2017) to ~$400 by "
            "Feb 2026, a ~90% loss. Bitcoin (BTC) trades at ~$107,000. Market consensus "
            "sided with Keiser's view that BCH was not 'the real Bitcoin.' The 'fraud' "
            "label was inflammatory hyperbole, but the directional call was correct."
        ),
        "evidence": "BCH price decline 90%+, BTC dominance maintained",
        "bias": 0.7,
        "source_type": "broadcast",
    },

    # --- FAILED PRICE PREDICTIONS ---
    {
        "statement": (
            "Bitcoin will reach $220,000 by the end of 2022"
        ),
        "source": "CryptoGlobe, January 2022 (BTC at ~$40K-$50K)",
        "category": "bitcoin_prediction",
        "date": "2022-01-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "Bitcoin ended 2022 at approximately $16,500 during the crypto winter "
            "following FTX collapse. Price went DOWN ~60% instead of up ~340% as "
            "predicted. One of Keiser's most spectacularly wrong predictions, made "
            "just before a major crash."
        ),
        "evidence": "BTC price Dec 31 2022: ~$16,500 vs $220K target",
        "bias": 0.95,
        "source_type": "interview",
        "source_url": "https://www.cryptoglobe.com/latest/2022/01/max-keiser-bitcoin-will-reach-220k-by-end-of-2022/",
    },
    {
        "statement": (
            "Bitcoin will reach $220,000 by the end of 2025"
        ),
        "source": "Daniela Cambone interview, December 2022 (goalpost move from 2022 target)",
        "category": "bitcoin_prediction",
        "date": "2022-12-01",
        "outcome_score": 0.45,
        "outcome_detail": (
            "As of February 2026, Bitcoin trades around $107,000, roughly 50% of the "
            "predicted target. Directionally correct (significant appreciation from ~$16K "
            "to $107K) but missed the specific target by half. Shows Keiser's pattern: "
            "make bold prediction, fail, move target date, claim partial victory."
        ),
        "evidence": "BTC price ~$107K vs $220K target by end 2025",
        "bias": 0.85,
        "source_type": "interview",
    },
    {
        "statement": (
            "Bitcoin will reach $400,000"
        ),
        "source": "Infowars interview with Alex Jones, February 2020 (BTC below $10K)",
        "category": "bitcoin_prediction",
        "date": "2020-02-01",
        "outcome_score": 0.3,
        "outcome_detail": (
            "As of February 2026 (6 years later), Bitcoin trades at ~$107,000, roughly "
            "25% of the predicted target. Significant appreciation occurred but far from "
            "target. Keiser quadrupled his previous $100K target with no fundamental "
            "justification beyond 'Bitcoin is scarce.'"
        ),
        "evidence": "BTC price ~$107K vs $400K target",
        "bias": 0.90,
        "source_type": "interview",
    },

    # --- FIAT COLLAPSE PREDICTIONS ---
    {
        "statement": (
            "The fiat U.S. dollar will collapse probably within 6 months"
        ),
        "source": "U.Today coverage, August 2024",
        "category": "macro_prediction",
        "date": "2024-08-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "As of February 2026 (18 months later), the U.S. dollar remains the global "
            "reserve currency and has not collapsed. DXY has fluctuated normally. This "
            "is a recurring pattern: perpetual predictions of imminent fiat collapse "
            "that never materialize on his timelines."
        ),
        "evidence": "DXY stability, USD still global reserve currency Feb 2026",
        "bias": 0.98,
        "source_type": "interview",
        "source_url": "https://u.today/bitcoiner-max-keiser-predicts-usd-crash-probably-within-6-months-details",
    },
    {
        "statement": (
            "All fiat currencies, including gold and silver, will go to zero "
            "against Bitcoin"
        ),
        "source": "Multiple interviews and tweets, 2021",
        "category": "macro_prediction",
        "date": "2021-01-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "As of February 2026, gold trades at all-time highs (~$2,000+), silver "
            "has appreciated, and both maintain value against Bitcoin. They have not "
            "gone to 'zero' in any meaningful sense. This also contradicts Keiser's "
            "own earlier silver advocacy and his more recent statement that silver "
            "will hit $150. Inconsistent positioning."
        ),
        "evidence": "Gold ATH ~$2000+, silver stable, fiat currencies functioning",
        "bias": 0.98,
        "source_type": "interview",
    },

    # --- OWN PROJECTS (THE BAD) ---
    {
        "statement": (
            "MaxCoin is a new cryptocurrency worth investing in"
        ),
        "source": "Keiser Report and Twitter promotion, February 2014",
        "category": "own_project",
        "date": "2014-02-01",
        "outcome_score": 0.05,
        "outcome_detail": (
            "MaxCoin (an altcoin named after himself) crashed after a brief pump, was "
            "'rebooted' in 2017, and trades at ~$0.001 by 2026. Investors who followed "
            "Keiser's bullish signals lost approximately 97%. Keiser later claimed 'it "
            "was his wife Stacy's idea' and went dark on the project. Some consider it "
            "a scam."
        ),
        "evidence": "MaxCoin price history (~97% loss), project abandonment",
        "bias": 0.95,
        "source_type": "broadcast",
        "source_url": "https://www.coindesk.com/markets/2014/02/05/max-keiser-inspired-altcoin-maxcoin-makes-its-debut",
    },
    {
        "statement": (
            "StartJOIN will monetize altruism through cryptocurrency-based crowdfunding"
        ),
        "source": "Cointelegraph interview, 2014",
        "category": "own_project",
        "date": "2014-06-01",
        "outcome_score": 0.1,
        "outcome_detail": (
            "StartJOIN never featured well-known companies. StartCoin went from $100K "
            "market cap (Jan 2015) to $5.1M (Jul 2015), then collapsed to $200K in 2017. "
            "The StartCoin page on MaxKeiser.com now returns 404. Co-founder Jamie Scott "
            "left. Another Keiser project that failed and left investors holding worthless "
            "tokens."
        ),
        "evidence": "StartCoin price collapse, site 404, co-founder departure",
        "bias": 0.90,
        "source_type": "interview",
    },

    # --- EL SALVADOR (THE UGLY) ---
    {
        "statement": (
            "Volcanic bonds will completely recapitalize the Salvadoran economy"
        ),
        "source": "El Salvador press coverage, February 2022",
        "category": "el_salvador",
        "date": "2022-02-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "The $1 billion volcano bonds have NEVER been issued as of February 2026. "
            "Originally planned for March 2022, then Q1 2024, they were repeatedly "
            "delayed and ultimately transformed into a private equity structure. Bitcoin "
            "City construction has not begun. The signature financing mechanism Keiser "
            "promoted never materialized."
        ),
        "evidence": "No volcano bond issuance, Bitcoin City unbuilt, repeated delays",
        "bias": 0.95,
        "source_type": "official",
        "source_url": "https://elsalvadorinenglish.com/2022/02/10/volcanic-bonds-will-completely-recapitalize-the-salvadoran-economy-max-keizer-crypto-investor-and-journalist/",
    },
    {
        "statement": (
            "El Salvador's Bitcoin adoption will be successful and transformative. "
            "This is the model for nation-state Bitcoin adoption"
        ),
        "source": "Multiple interviews as National Bitcoin Office advisor, 2022-2024",
        "category": "el_salvador",
        "date": "2022-06-01",
        "outcome_score": 0.15,
        "outcome_detail": (
            "By 2024, only 8% of Salvadorans used Bitcoin for payments (down from 24.4% "
            "in 2022 and 12% in 2023). El Salvador agreed to limit Bitcoin involvement "
            "with the IMF in 2024, removing mandatory merchant acceptance. In 2025, "
            "Bitcoin was rescinded as legal tender. The Economist declared the experiment "
            "a 'failure.' Adoption went the wrong direction under Keiser's advisory role."
        ),
        "evidence": "Adoption drop 24.4%->8%, legal tender rescinded 2025, IMF deal",
        "bias": 0.85,
        "source_type": "interview",
    },

    # --- SILVER CAMPAIGN ---
    {
        "statement": (
            "Buy silver to crash JP Morgan by forcing them to cover their short "
            "position. This will bring down the bank"
        ),
        "source": "Keiser Report 'Crash JP Morgan Buy Silver' campaign, 2010-2012",
        "category": "activism",
        "date": "2010-11-01",
        "outcome_score": 0.25,
        "outcome_detail": (
            "Campaign temporarily drove silver from $17 to $50, but JP Morgan sold "
            "fresh naked shorts and killed the rally. Silver crashed back down. JP "
            "Morgan did not collapse or face significant consequences from the campaign. "
            "Some credit for attempting activist pressure on silver manipulation, but "
            "the stated goal of 'crashing' a major bank was wildly unrealistic."
        ),
        "evidence": "Silver price spike $17->$50->crash, JP Morgan unaffected",
        "bias": 0.80,
        "source_type": "broadcast",
    },

    # --- ALTCOIN CRITIQUE ---
    {
        "statement": (
            "Most or all altcoins are going to pennies or go out of existence, "
            "because all of that cash is going to flow to Bitcoin"
        ),
        "source": "Cointelegraph and multiple interviews, 2019",
        "category": "altcoin_critique",
        "date": "2019-06-01",
        "outcome_score": 0.5,
        "outcome_detail": (
            "Many altcoins from 2019 have indeed failed or lost 90%+ value. However, "
            "Ethereum ($3,000+), Solana ($150+), and other major altcoins remain viable "
            "and thriving. Bitcoin dominance increased but didn't achieve total dominance. "
            "Partly right about small-cap altcoin failures, wrong about total wipeout. "
            "Ironic given Keiser's own failed altcoin launches (MaxCoin, StartCoin)."
        ),
        "evidence": "Many altcoins died, but ETH/SOL/etc thriving; BTC dominance partial",
        "bias": 0.90,
        "source_type": "interview",
    },
]

# ──────────────────────────────────────────────────────────────────────

print("=" * 70)
print("SAY/DO POC: Max Keiser Credibility Index")
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
    ("Bitcoin will reach $500,000 by 2027", "bitcoin_prediction"),
    ("El Salvador will become a Bitcoin hub", "el_salvador"),
    ("The US dollar will collapse within 2 years", "macro_prediction"),
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
    if 0.15 <= cred <= 0.45:
        print(f"  PASS: Credibility score {cred:.3f} in target range [0.15, 0.45]")
    else:
        print(f"  NOTE: Credibility score {cred:.3f} outside target range [0.15, 0.45]")
else:
    print("  WARN: No credibility score computed")

print(f"\n  Contradiction score: {profile['contradiction_score']:.3f}")
print(f"  Total kept: {profile['outcomes_followed']}/{profile['total_statements']}")

print("\n" + "=" * 70)
print("POC COMPLETE")
print("=" * 70)
