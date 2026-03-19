#!/usr/bin/env python3
"""Say/Do POC: Stani Kulechov (Aave) Credibility Index.

Populates the Say/Do engine with Stani Kulechov's public statements
and their known outcomes, then generates the full credibility profile.

Validation target: ~0.74 credibility. Exceptional technical delivery on
core Aave protocol (V1/V2/V3, flash loans, security), but misses on
ancillary ventures (Aave Arc, Avara, Lens, GHO initial peg).

All statements sourced from public record (tweets, interviews, blog posts,
conference talks, governance forums).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omega.sqlite_store import SQLiteStore
from omega.saydo.engine import get_saydo_engine, _engine_instance
import omega.saydo.engine as eng_mod
import omega.bridge as bridge

DB_PATH = Path(__file__).parent.parent / "data" / "poc_saydo_stani.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

if DB_PATH.exists():
    DB_PATH.unlink()

store = SQLiteStore(db_path=str(DB_PATH))
bridge._store_instance = store
eng_mod._engine_instance = None

engine = get_saydo_engine()

ENTITY = "Stani Kulechov"
ENTITY_TYPE = "person"

DATA = [
    # --- CORE PROTOCOL DELIVERY ---
    {
        "statement": (
            "V2 takes DeFi composability beyond what we have seen. V2 will introduce "
            "the ability to swap debt from one currency to another and the ability to "
            "swap collateral without returning the loan"
        ),
        "source": "CoinDesk / Aave announcement, August 14, 2020",
        "category": "product_delivery",
        "date": "2020-08-14",
        "outcome_score": 0.95,
        "outcome_detail": (
            "Aave V2 launched on mainnet December 3, 2020. All promised features were "
            "delivered: collateral swapping, one-step repayment with collateral, debt "
            "tokenization, batch flash loans, and gas optimizations (up to 50% reduction). "
            "V2 became the dominant DeFi lending protocol. Full delivery on a tight timeline."
        ),
        "evidence": "Aave V2 mainnet launch Dec 3 2020, feature completeness verified",
        "bias": 0.3,
        "source_type": "tech_media",
    },
    {
        "statement": (
            "Flash Loan is a feature meant to empower the developer community. "
            "We always had this thesis that we want to unlock value and use capital "
            "as efficiently as possible"
        ),
        "source": "CoinGecko Podcast, Episode 21, March 2020",
        "category": "product_delivery",
        "date": "2020-03-01",
        "outcome_score": 1.0,
        "outcome_detail": (
            "Flash loans became one of the most important DeFi primitives. Enabled "
            "liquidation bots, arbitrage strategies, collateral swaps, and entirely new "
            "product categories. Aave processed $133M+ in flash loans in a single day "
            "during 2020. The feature became widely adopted and copied across DeFi. "
            "Kulechov correctly identified flash loans as transformative before the "
            "market validated it."
        ),
        "evidence": "Flash loan adoption data, $133M single-day volume, cross-protocol adoption",
        "bias": 0.25,
        "source_type": "interview",
    },
    {
        "statement": (
            "V3 is mostly about risk awareness and capital efficiency. You could deposit "
            "on mainnet but borrow from Polygon and repay on Avalanche, all under the hood"
        ),
        "source": "Smart Contract Summit, November 2021 / CoinDesk March 2022",
        "category": "product_delivery",
        "date": "2021-11-01",
        "outcome_score": 0.80,
        "outcome_detail": (
            "Aave V3 launched March 16, 2022 on six chains (Polygon, Arbitrum, Avalanche, "
            "Fantom, Harmony, Optimism). Efficiency Mode, Isolation Mode, and Portal "
            "cross-chain features all delivered. However, Portal cross-chain had limited "
            "initial adoption and the seamless cross-chain vision took longer to materialize "
            "than implied. Core technical delivery was strong; UX vision was ahead of "
            "infrastructure reality."
        ),
        "evidence": "V3 launch March 16 2022, 6 chains, eMode/Isolation/Portal delivered",
        "bias": 0.35,
        "source_type": "tech_media",
    },

    # --- SECURITY ---
    {
        "statement": (
            "The Aave protocol is safe. It has never experienced an exploit in its "
            "five-year history. The protocol operated flawlessly, automatically "
            "liquidating a record $180M worth of collateral in just one hour, "
            "without any human intervention"
        ),
        "source": "Various interviews and X posts, 2024-2025",
        "category": "security",
        "date": "2024-06-01",
        "outcome_score": 0.90,
        "outcome_detail": (
            "Aave's core protocol has indeed never suffered a major exploit, remarkable "
            "for a protocol that has processed trillions in cumulative volume over 5+ "
            "years. The $180M liquidation event was real and demonstrated protocol "
            "resilience. A minor $56K periphery contract hack occurred in 2024 (tip jar) "
            "which Kulechov dismissed as 'a tip jar arbed.' Core safety claim holds "
            "up extremely well."
        ),
        "evidence": "Zero core exploits in 5+ years, $3T+ cumulative volume, $180M stress test",
        "bias": 0.25,
        "source_type": "interview",
    },

    # --- GHO STABLECOIN ---
    {
        "statement": (
            "The point of the current model is growing debt nominated in GHO, which "
            "has been growing quite well. I would say the focus on peg should come later"
        ),
        "source": "X (Twitter), August 2023",
        "category": "stablecoin",
        "date": "2023-08-01",
        "outcome_score": 0.55,
        "outcome_detail": (
            "GHO launched July 15, 2023 and traded below $1 for approximately six months "
            "(hitting $0.96 at worst during the Curve exploit). The 'peg should come later' "
            "framing was criticized as dismissive. However, GHO did eventually reach peg "
            "by February 2024 and grew to $483M market cap in 2025 (230% growth YTD). "
            "Long-term strategy played out, but initial dismissal of peg concerns was "
            "misleading for a stablecoin."
        ),
        "evidence": "GHO launch Jul 2023, sub-peg trading, $483M cap by 2025",
        "bias": 0.55,
        "source_type": "social_media",
    },
    {
        "statement": (
            "GHO will be differentiated from other stablecoins because it is backed by "
            "a diverse range of crypto assets and generates revenue directly for the Aave DAO"
        ),
        "source": "Decrypt interview, October 2022",
        "category": "stablecoin",
        "date": "2022-10-01",
        "outcome_score": 0.70,
        "outcome_detail": (
            "GHO launched as overcollateralized and revenue-accruing to the DAO. By 2025, "
            "reached $483M market cap and began multi-chain expansion (Aptos, CCIP bridging). "
            "Differentiation claims were largely accurate. Integration with BlackRock's BUIDL "
            "announced in 2024. Delivered on architecture; scale aspirations still developing. "
            "Remains far smaller than DAI, USDC, or USDT."
        ),
        "evidence": "GHO $483M cap, multi-chain expansion, BlackRock BUIDL integration",
        "bias": 0.30,
        "source_type": "tech_media",
    },

    # --- VENTURES OUTSIDE CORE ---
    {
        "statement": (
            "The ownership of content and profiles should belong to you in the way "
            "that DeFi belongs to you. Your followers are not stuck anymore on platforms"
        ),
        "source": "Permissionless conference / LinkedIn, 2022 (Lens Protocol launch)",
        "category": "social_protocol",
        "date": "2022-05-01",
        "outcome_score": 0.45,
        "outcome_detail": (
            "Lens Protocol launched on Polygon May 2022 with NFT-based profiles and open "
            "social graph. Attracted micro-communities and apps (Orb, Phaver). Never achieved "
            "mainstream adoption. Lens V2 launched Nov 2023, V3/Lens Chain mainnet April 2025. "
            "Ultimately, Kulechov transferred stewardship to Mask Network in January 2026 "
            "and wound down the Avara brand. Technical vision delivered, but product never "
            "reached mass adoption, and Kulechov exited the effort."
        ),
        "evidence": "Lens launch May 2022, handoff to Mask Network Jan 2026, Avara wind-down",
        "bias": 0.40,
        "source_type": "conference",
    },
    {
        "statement": (
            "Aave Arc allows institutions to interact with the Aave Protocol on their "
            "own separate and permissioned liquidity pool where every user has been verified"
        ),
        "source": "Aave / Fireblocks announcement, 2021",
        "category": "institutional",
        "date": "2021-11-01",
        "outcome_score": 0.25,
        "outcome_detail": (
            "Aave Arc launched January 2022 with Fireblocks whitelisting 30 institutions "
            "(SEBA Bank, Celsius, CoinShares, GSR, Wintermute). TVL peaked at only ~$8M "
            "and eventually went to zero. Analysis from Aave's governance forum suggested "
            "only 1-2 institutions actually used it. Clear failure: product built and "
            "shipped but market demand was not there. Institutional DeFi thesis was premature."
        ),
        "evidence": "Aave Arc TVL peaked $8M, declined to zero, 1-2 active institutions",
        "bias": 0.45,
        "source_type": "tech_media",
    },
    {
        "statement": (
            "Credit delegation could become a wholesale debt market. Any facility in "
            "DeFi, CeFi, or traditional finance could source part of its liquidity from Aave"
        ),
        "source": "Decrypt interview, August 2020",
        "category": "product_delivery",
        "date": "2020-08-01",
        "outcome_score": 0.40,
        "outcome_detail": (
            "Credit delegation launched with DeversiFi as first borrower July 2020, "
            "included in V2. Feature exists and works technically. Never became the "
            "'wholesale debt market' Kulechov envisioned. Usage remained niche; ~75% of "
            "depositors never utilized credit delegation. Feature persists in V3 but is "
            "not a significant growth driver. Technical delivery succeeded; market thesis "
            "did not materialize."
        ),
        "evidence": "Credit delegation launch, niche adoption, persistence in V3",
        "bias": 0.45,
        "source_type": "tech_media",
    },
    {
        "statement": (
            "Avara will do more beyond DeFi, bringing web3 to all users globally with "
            "different kinds of use cases"
        ),
        "source": "TechCrunch, November 2023 (rebrand announcement)",
        "category": "strategy",
        "date": "2023-11-01",
        "outcome_score": 0.20,
        "outcome_detail": (
            "Avara brand was retired in February 2026, just ~2 years later. Family wallet "
            "wound down. Lens Protocol handed off to Mask Network. Company reverted to "
            "'Aave Labs' and refocused entirely on DeFi lending. Strategic reversal: the "
            "'beyond DeFi' thesis was abandoned in favor of doubling down on core competency. "
            "Kulechov acknowledged this pivot publicly."
        ),
        "evidence": "Avara brand retired Feb 2026, Family wallet shut down, Lens handed off",
        "bias": 0.40,
        "source_type": "tech_media",
    },

    # --- GOVERNANCE ---
    {
        "statement": (
            "No one cares about Aave more than I do. Open debate is a feature of DeFi "
            "governance and is not a symptom of misalignment"
        ),
        "source": "X (Twitter) / CryptoNewsZ, December 2025",
        "category": "governance",
        "date": "2025-12-01",
        "outcome_score": 0.55,
        "outcome_detail": (
            "Statement came during heated governance dispute where Kulechov purchased $15M "
            "in AAVE tokens and was accused of a 'governance attack.' A proposal to transfer "
            "brand assets to the DAO was rejected (55% against). Critics warned governance "
            "was becoming 'theater.' Kulechov subsequently proposed 'Aave Will Win' framework "
            "routing 100% of product revenue to DAO, addressing many concerns. Decentralization "
            "claim partially credible but Kulechov's outsized token holdings create real "
            "centralization concerns."
        ),
        "evidence": "$15M AAVE purchase, governance vote results, 'Aave Will Win' framework",
        "bias": 0.55,
        "source_type": "social_media",
    },

    # --- REGULATORY ---
    {
        "statement": (
            "DeFi has faced unfair regulatory pressure in recent years. We're glad to "
            "put this behind us as we enter a new era where developers can truly build "
            "the future of finance"
        ),
        "source": "X (Twitter), December 2025 (after SEC probe closure)",
        "category": "regulatory",
        "date": "2025-12-01",
        "outcome_score": 0.85,
        "outcome_detail": (
            "SEC closed its 4-year investigation into Aave without enforcement action "
            "(confirmed in August 2025 letter). Aave survived the probe intact. "
            "Characterization of regulatory environment as 'unfair' reflects widely-held "
            "industry view. Factual claim validated by outcome."
        ),
        "evidence": "SEC investigation closed Aug 2025, no enforcement action",
        "bias": 0.35,
        "source_type": "social_media",
    },

    # --- FORWARD-LOOKING ---
    {
        "statement": (
            "Embedded DeFi is a trillion-dollar opportunity for fintechs"
        ),
        "source": "X (Twitter), October 2025",
        "category": "strategy",
        "date": "2025-10-01",
        "outcome_score": 0.60,
        "outcome_detail": (
            "Too early to fully evaluate. Aave's TVL growth from $8B to $47B in 2024-2025, "
            "MetaMask's integration of Aave yields, and growing institutional DeFi adoption "
            "suggest directional thesis is correct. Aave commands ~60% of DeFi lending "
            "market share. 'Trillion dollar' framing is aspirational and unverifiable on "
            "current timelines, but trend line supports direction."
        ),
        "evidence": "Aave TVL growth $8B->$47B, MetaMask integration, 60% market share",
        "bias": 0.45,
        "source_type": "social_media",
    },
    {
        "statement": (
            "Aave V4 will introduce a hub-and-spoke unified liquidity model with "
            "a full rollout planned for early 2026 and a goal of onboarding the "
            "protocol's first million users"
        ),
        "source": "The Block / Aave master plan, December 2025",
        "category": "product_delivery",
        "date": "2025-12-01",
        "outcome_score": 0.50,
        "outcome_detail": (
            "As of February 2026, V4 mainnet targeted for Q1 2026. This is an ongoing "
            "promise. The 'first million users' goal is ambitious. Kulechov has a strong "
            "track record of delivering major protocol versions (V1, V2, V3 all shipped), "
            "so reasonable confidence in technical delivery, though timelines may slip."
        ),
        "evidence": "V4 roadmap Q1 2026, prior delivery track record (V1/V2/V3)",
        "bias": 0.40,
        "source_type": "tech_media",
    },
]

# ──────────────────────────────────────────────────────────────────────

print("=" * 70)
print("SAY/DO POC: Stani Kulechov (Aave) Credibility Index")
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
    ("Aave V4 will launch on mainnet by Q1 2026", "product_delivery"),
    ("GHO will reach $1 billion market cap in 2026", "stablecoin"),
    ("Aave will maintain its zero-exploit security record through 2026", "security"),
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
    if 0.55 <= cred <= 0.85:
        print(f"  PASS: Credibility score {cred:.3f} in target range [0.55, 0.85]")
    else:
        print(f"  NOTE: Credibility score {cred:.3f} outside target range [0.55, 0.85]")
else:
    print("  WARN: No credibility score computed")

print(f"\n  Contradiction score: {profile['contradiction_score']:.3f}")
print(f"  Total kept: {profile['outcomes_followed']}/{profile['total_statements']}")

print("\n" + "=" * 70)
print("POC COMPLETE")
print("=" * 70)
