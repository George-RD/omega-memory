#!/usr/bin/env python3
"""Say/Do POC: Hayden Adams (Uniswap) Credibility Index.

Populates the Say/Do engine with Hayden Adams' public statements
and their known outcomes, then generates the full credibility profile.

Validation target: ~0.71 credibility. Strong builder who ships every
major version, but uses self-serving framing on decentralization/open-source
and has optimistic timelines.

All statements sourced from public record (tweets, blog posts, conference
talks, SEC filings).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omega.sqlite_store import SQLiteStore
from omega.saydo.engine import get_saydo_engine, _engine_instance
import omega.saydo.engine as eng_mod
import omega.bridge as bridge

DB_PATH = Path(__file__).parent.parent / "data" / "poc_saydo_hayden.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

if DB_PATH.exists():
    DB_PATH.unlink()

store = SQLiteStore(db_path=str(DB_PATH))
bridge._store_instance = store
eng_mod._engine_instance = None

engine = get_saydo_engine()

ENTITY = "Hayden Adams"
ENTITY_TYPE = "person"

DATA = [
    # --- PRODUCT DELIVERY ---
    {
        "statement": (
            "Excited to announce the launch of @UniswapExchange! It's a protocol "
            "for automated exchange of ERC20 tokens on Ethereum"
        ),
        "source": "Twitter @haydenzadams, November 2, 2018 (Devcon 4)",
        "category": "product_delivery",
        "date": "2018-11-02",
        "outcome_score": 1.0,
        "outcome_detail": (
            "Uniswap V1 deployed to Ethereum mainnet on November 2, 2018 at Devcon 4. "
            "About $30,000 deposited into contracts by a single provider across 3 tokens. "
            "The protocol worked as described and became the foundation for all subsequent "
            "versions and the entire AMM category in DeFi."
        ),
        "evidence": "Uniswap V1 deployment on Ethereum, transaction history",
        "bias": 0.1,
        "source_type": "social_media",
    },
    {
        "statement": (
            "I don't think the insane efficiency of Uniswap v3 has sunk in yet. "
            "The equation for calculating efficiency of a concentrated v3 position "
            "relative to v2 provides up to 4000x capital efficiency"
        ),
        "source": "Twitter @haydenzadams, April 8, 2021",
        "category": "product_delivery",
        "date": "2021-04-08",
        "outcome_score": 0.5,
        "outcome_detail": (
            "Uniswap V3 launched May 2021 with concentrated liquidity providing up to "
            "4000x theoretical capital efficiency vs V2. However, research by Bancor "
            "(November 2021) found over 50% of V3 LPs lost money due to amplified "
            "impermanent loss. Pools generated $199.3M in fees but incurred $260.1M in "
            "impermanent loss. Mathematical efficiency was real, but practical outcome "
            "for most LPs was negative."
        ),
        "evidence": "Bancor IL study Nov 2021, V3 fee/loss data",
        "bias": 0.6,
        "source_type": "social_media",
    },
    {
        "statement": (
            "Today I'm incredibly excited to share our vision for Uniswap v4 and "
            "why we've decided to build in public. We see Uniswap as core financial "
            "infrastructure and think it should be built in public with community "
            "feedback and contribution"
        ),
        "source": "Twitter @haydenzadams, June 13, 2023",
        "category": "product_delivery",
        "date": "2023-06-13",
        "outcome_score": 0.8,
        "outcome_detail": (
            "Uniswap V4 was built more openly than previous versions, with draft code "
            "released for community feedback. Over 150 hooks developed by external "
            "developers. V4 launched January 30, 2025 on 10+ chains including Ethereum, "
            "Polygon, Arbitrum, Base, and BNB Chain. Hooks architecture delivered as "
            "promised. Deducting slightly because launch missed Q3 2024 target by ~5 months."
        ),
        "evidence": "V4 launch Jan 30 2025, 150+ hooks developed, multi-chain deployment",
        "bias": 0.2,
        "source_type": "social_media",
        "source_url": "https://x.com/haydenzadams/status/1668625940681998339",
    },

    # --- TIMELINE ACCURACY ---
    {
        "statement": (
            "Uniswap v4 is targeted for Q3 2024 release, with the Ethereum Dencun "
            "upgrade as a critical deciding factor"
        ),
        "source": "Uniswap Foundation announcement, February 15, 2024",
        "category": "timeline",
        "date": "2024-02-15",
        "outcome_score": 0.5,
        "outcome_detail": (
            "V4 missed the Q3 2024 target. On January 2, 2025, Uniswap teased 'v4 is "
            "coming soon' without a specific date. It launched January 30, 2025, "
            "approximately 4-5 months late. Delay attributed to additional security "
            "audits and a $15.5M bug bounty program. Product shipped with all promised "
            "features but significantly behind schedule."
        ),
        "evidence": "V4 launch date Jan 30 2025 vs Q3 2024 target",
        "bias": 0.3,
        "source_type": "official",
    },

    # --- SEC / REGULATORY ---
    {
        "statement": (
            "Today Uniswap Labs received a Wells notice from the SEC. I'm not surprised. "
            "Just annoyed, disappointed, and ready to fight. I am confident that the "
            "products we offer are legal"
        ),
        "source": "Twitter @haydenzadams, April 10, 2024",
        "category": "regulatory",
        "date": "2024-04-10",
        "outcome_score": 0.9,
        "outcome_detail": (
            "Uniswap Labs fought the SEC. Filed a formal Wells Notice response. On "
            "February 25, 2025, the SEC dropped the investigation entirely without "
            "filing enforcement charges. COO Mary-Catherine Lader revealed they spent "
            "'tens of millions' on legal defense. The fight was won, though largely "
            "aided by a change in SEC leadership and administration."
        ),
        "evidence": "SEC dropped investigation Feb 25 2025, Wells Notice response filed",
        "bias": 0.3,
        "source_type": "social_media",
        "source_url": "https://x.com/haydenzadams/status/1778126466984575166",
    },
    {
        "statement": (
            "This fight will take years, may go all the way to the Supreme Court, "
            "and the future of financial technology hangs in the balance"
        ),
        "source": "Twitter @haydenzadams, April 10, 2024 (same Wells Notice thread)",
        "category": "regulatory",
        "date": "2024-04-10",
        "outcome_score": 0.3,
        "outcome_detail": (
            "The case was dropped by the SEC in February 2025, roughly 10 months later. "
            "It did not take years and did not go to the Supreme Court. Resolution was "
            "far faster and more favorable than predicted. He was wrong in a way that "
            "benefited him (situation better than predicted)."
        ),
        "evidence": "SEC dropped investigation ~10 months after Wells Notice",
        "bias": 0.5,
        "source_type": "social_media",
    },

    # --- DECENTRALIZATION / OPEN SOURCE ---
    {
        "statement": (
            "Uniswap Protocol is fully decentralized permissionless smart contracts "
            "on Ethereum. Uniswap Interface is open source GPL code base"
        ),
        "source": "Twitter @haydenzadams, July 24, 2021",
        "category": "decentralization",
        "date": "2021-07-24",
        "outcome_score": 0.7,
        "outcome_detail": (
            "Protocol smart contracts remain permissionless and immutable on Ethereum. "
            "However, Uniswap Labs introduced a 0.15% interface fee in October 2023 "
            "and has delisted tokens from the frontend. The practical user experience "
            "is increasingly shaped by Labs' centralized decisions (fees, token "
            "delisting), creating a gap between decentralization narrative and "
            "user-facing reality."
        ),
        "evidence": "Protocol remains permissionless; interface fee Oct 2023; token delisting",
        "bias": 0.5,
        "source_type": "social_media",
    },
    {
        "statement": (
            "Uniswap v4 code is open sourced for community contribution and feedback"
        ),
        "source": "Twitter and blog, June 2023 (V4 announcement)",
        "category": "decentralization",
        "date": "2023-06-13",
        "outcome_score": 0.4,
        "outcome_detail": (
            "V4 uses a Business Source License (BSL) with a 4-year proprietary period, "
            "not true open source. Developers criticized the BSL: Gabriel Shapiro called "
            "it a 'tax on innovation,' Scott Lewis said 'if anyone else misrepresented "
            "the truth like this they would be torn to shreds.' Adams backtracked to "
            "'source available' after community backlash. V3's BSL did convert to GPL "
            "as designed (April 2023), so the eventual conversion is credible."
        ),
        "evidence": "BSL license on V4, community backlash, Adams correction to 'source available'",
        "bias": 0.7,
        "source_type": "social_media",
    },

    # --- GOVERNANCE ---
    {
        "statement": (
            "UNI governance enables shared community ownership of the Uniswap protocol"
        ),
        "source": "Uniswap blog and social media, September 2020 (UNI launch)",
        "category": "governance",
        "date": "2020-09-01",
        "outcome_score": 0.5,
        "outcome_detail": (
            "400 UNI tokens airdropped to every past user. Governance technically exists. "
            "However, Adams himself later stated (November 2025): 'for the past 5 years "
            "Labs has been unable to meaningfully participate in governance.' Fee switch "
            "was blocked for years by large holders like a16z. UNIfication proposal "
            "passed with 125.3M votes for vs 742 against, suggesting governance dominated "
            "by large holders rather than true community ownership."
        ),
        "evidence": "UNI airdrop Sep 2020, fee switch delays, UNIfication vote distribution",
        "bias": 0.6,
        "source_type": "official",
    },
    {
        "statement": (
            "Today I'm making my first proposal to Uniswap governance: UNIfication "
            "turns on protocol fees and aligns incentives across the ecosystem"
        ),
        "source": "Twitter @haydenzadams, November 10, 2025",
        "category": "governance",
        "date": "2025-11-10",
        "outcome_score": 0.9,
        "outcome_detail": (
            "UNIfication passed governance with 125.3M UNI votes for vs 742 against. "
            "Protocol fees activated, 100M UNI burned from treasury, Labs' interface "
            "fees eliminated, Labs gets 20M UNI annual budget. Labs became formally "
            "aligned with governance under a legally binding agreement. One of the most "
            "significant governance actions in DeFi history."
        ),
        "evidence": "UNIfication governance vote, protocol fee activation, 100M UNI burn",
        "bias": 0.4,
        "source_type": "social_media",
    },

    # --- PRODUCT EXPANSION ---
    {
        "statement": (
            "This interface fee is one of the lowest in the industry and will allow "
            "us to continue to research, develop, build, ship, improve, and expand "
            "crypto and DeFi"
        ),
        "source": "Twitter @haydenzadams, October 2023",
        "category": "financial_strategy",
        "date": "2023-10-17",
        "outcome_score": 0.6,
        "outcome_detail": (
            "The 0.15% fee was implemented October 17, 2023. Frontend market share "
            "came under pressure. Later, UNIfication (November 2025) eliminated the "
            "interface fee in exchange for protocol-level fees and 20M UNI annual "
            "budget. The fee was a temporary revenue bridge, not a permanent structure. "
            "Fee did generate revenue for Labs as claimed."
        ),
        "evidence": "Interface fee implementation Oct 2023, elimination via UNIfication",
        "bias": 0.6,
        "source_type": "social_media",
    },
    {
        "statement": (
            "UniswapX offers better prices by aggregating liquidity sources, gas-free "
            "swaps, and protection against MEV"
        ),
        "source": "Uniswap Blog, EthCC Paris, July 17, 2023",
        "category": "product_delivery",
        "date": "2023-07-17",
        "outcome_score": 0.8,
        "outcome_detail": (
            "UniswapX launched and is operational. Uses Dutch auctions with competing "
            "fillers for better prices. MEV protection works (off-chain orders can't be "
            "sandwiched). Gas-free swaps delivered (fillers pay gas). Aggregates on-chain "
            "and off-chain liquidity. Cross-chain swaps (a promised feature) delayed but "
            "eventually launched October 2024."
        ),
        "evidence": "UniswapX operational, MEV protection verified, cross-chain Oct 2024",
        "bias": 0.2,
        "source_type": "official",
    },
    {
        "statement": (
            "We're entering a cross-chain world. Unichain will make that feel cohesive "
            "to users"
        ),
        "source": "The Block interview, February 11, 2025",
        "category": "product_delivery",
        "date": "2025-02-11",
        "outcome_score": 0.7,
        "outcome_detail": (
            "Unichain launched on mainnet February 11, 2025 as an Ethereum L2 (OP Stack). "
            "V4 deployed across 10+ chains. Cross-chain vision is being actively executed, "
            "though Unichain is early in adoption and the 'cohesive cross-chain UX' "
            "is still aspirational rather than fully realized."
        ),
        "evidence": "Unichain mainnet launch Feb 11 2025, V4 multi-chain deployment",
        "bias": 0.3,
        "source_type": "interview",
    },

    # --- VALUES / ADVOCACY ---
    {
        "statement": (
            "I think freedom is worth fighting for. I think DeFi is worth fighting for"
        ),
        "source": "Twitter @haydenzadams, April 10, 2024 (Wells Notice thread)",
        "category": "values",
        "date": "2024-04-10",
        "outcome_score": 0.7,
        "outcome_detail": (
            "Adams backed this with action: Uniswap spent 'tens of millions' on legal "
            "defense, continued building throughout the SEC investigation, launched V4, "
            "Unichain, and UNIfication. However, the 'freedom' framing is somewhat "
            "contradicted by BSL licensing (restricting code use for 4 years) and "
            "centralizing interface control."
        ),
        "evidence": "Legal defense spending, continued product launches during SEC probe",
        "bias": 0.5,
        "source_type": "social_media",
    },
]

# ──────────────────────────────────────────────────────────────────────

print("=" * 70)
print("SAY/DO POC: Hayden Adams (Uniswap) Credibility Index")
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
    ("Uniswap v5 will ship on time within 12 months of announcement", "product_delivery"),
    ("Uniswap protocol will remain fully decentralized and permissionless", "decentralization"),
    ("UNI holders will receive 100% of protocol fee revenue", "governance"),
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
    if 0.55 <= cred <= 0.80:
        print(f"  PASS: Credibility score {cred:.3f} in target range [0.55, 0.80]")
    else:
        print(f"  NOTE: Credibility score {cred:.3f} outside target range [0.55, 0.80]")
else:
    print("  WARN: No credibility score computed")

print(f"\n  Contradiction score: {profile['contradiction_score']:.3f}")
print(f"  Total kept: {profile['outcomes_followed']}/{profile['total_statements']}")

print("\n" + "=" * 70)
print("POC COMPLETE")
print("=" * 70)
