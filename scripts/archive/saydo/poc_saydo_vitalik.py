#!/usr/bin/env python3
"""Say/Do POC: Vitalik Buterin Credibility Index.

Populates the Say/Do engine with Vitalik Buterin's public statements
and their known outcomes, then generates the full credibility profile.

Validation anchor: Vitalik should score ABOVE 0.75 credibility.
If he doesn't, something is broken in the credibility system.

All statements sourced from public record (blog posts, tweets, interviews,
Ethereum governance records). Uses the new credibility features: specificity,
bias, partial outcomes, deadlines, source_url, source_type.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omega.sqlite_store import SQLiteStore
from omega.saydo.engine import get_saydo_engine, _engine_instance
import omega.saydo.engine as eng_mod
import omega.bridge as bridge

DB_PATH = Path(__file__).parent.parent / "data" / "poc_saydo_vitalik.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Fresh DB each run for reproducibility
if DB_PATH.exists():
    DB_PATH.unlink()

store = SQLiteStore(db_path=str(DB_PATH))
bridge._store_instance = store
eng_mod._engine_instance = None

engine = get_saydo_engine()

ENTITY = "Vitalik Buterin"
ENTITY_TYPE = "person"

# ──────────────────────────────────────────────────────────────────────
# STATEMENTS + OUTCOMES
# Each dict has: statement, source, category, date, followed_through or
# outcome_score, outcome_detail, evidence, and credibility fields:
# bias, deadline, source_url, source_type
# ──────────────────────────────────────────────────────────────────────

DATA = [
    # ─── TECHNICAL PROMISES: DELIVERED ───
    {
        "statement": (
            "Ethereum will transition from proof-of-work to proof-of-stake consensus. "
            "The Merge will reduce energy consumption by approximately 99.95%"
        ),
        "source": "Ethereum roadmap, multiple blog posts and conference talks 2016-2022",
        "category": "technical_roadmap",
        "date": "2020-12-01",
        "outcome_score": 1.0,
        "outcome_detail": (
            "The Merge executed successfully on September 15, 2022 with zero downtime. "
            "Ethereum transitioned from PoW to PoS, reducing energy consumption by an "
            "estimated 99.95%. Buterin called it 'a big moment for the Ethereum ecosystem' "
            "and said 'a sky that has been cloudy for almost a decade finally cleared.'"
        ),
        "evidence": "Ethereum Merge event Sept 15 2022, energy consumption data",
        "bias": 0.1,  # Founder but transparent about risks
        "source_type": "official",
        "source_url": "https://ethereum.org/en/roadmap/merge/",
    },
    {
        "statement": (
            "EIP-1559 will introduce a base fee that is burned, making ETH deflationary "
            "during high usage periods and improving fee market predictability"
        ),
        "source": "EIP-1559 proposal co-authored by Buterin, discussed 2019-2021",
        "category": "technical_roadmap",
        "date": "2019-04-01",
        "outcome_score": 1.0,
        "outcome_detail": (
            "EIP-1559 activated in the London hard fork on August 5, 2021. The base fee "
            "burn mechanism works as described. Over 4 million ETH burned since activation. "
            "Fee predictability significantly improved. ETH became net deflationary during "
            "high-usage periods post-Merge."
        ),
        "evidence": "London hard fork Aug 2021, ultrasound.money burn tracker",
        "bias": 0.1,
        "deadline": "2021-12-31",
        "source_type": "official",
        "source_url": "https://eips.ethereum.org/EIPS/eip-1559",
    },
    {
        "statement": (
            "We should adopt a rollup-centric Ethereum roadmap. Rollups will be the "
            "dominant scaling solution, and Ethereum should optimize for data availability "
            "rather than execution sharding"
        ),
        "source": "Blog post 'A rollup-centric ethereum roadmap', October 2020",
        "category": "technical_roadmap",
        "date": "2020-10-02",
        "outcome_score": 0.9,
        "outcome_detail": (
            "The rollup-centric roadmap was adopted and became Ethereum's official scaling "
            "strategy. Rollups (Arbitrum, Optimism, zkSync, StarkNet, Base) grew to process "
            "more transactions than Ethereum L1. However, Buterin himself acknowledged in "
            "2026 that L2s 'decentralized far slower' than anticipated, calling for a new path. "
            "Core thesis validated but honest about limitations."
        ),
        "evidence": "L2Beat TVL data, Ethereum Foundation roadmap, Buterin 2026 reassessment",
        "bias": 0.1,
        "source_type": "blog",
        "source_url": "https://ethereum-magicians.org/t/a-rollup-centric-ethereum-roadmap/4698",
    },
    {
        "statement": (
            "EIP-4844 (Proto-Danksharding) will introduce blob-carrying transactions "
            "that reduce L2 data costs by at least 10x"
        ),
        "source": "EIP-4844 co-authored by Buterin et al, February 2022",
        "category": "technical_roadmap",
        "date": "2022-02-01",
        "outcome_score": 1.0,
        "outcome_detail": (
            "EIP-4844 activated in the Dencun upgrade on March 13, 2024. L2 transaction "
            "costs dropped by over 100x in many cases, far exceeding the 10x target. "
            "Blob transactions work as specified. Major milestone for Ethereum scaling."
        ),
        "evidence": "Dencun upgrade March 2024, L2 fee data post-Dencun",
        "bias": 0.1,
        "deadline": "2024-06-30",
        "source_type": "official",
        "source_url": "https://eips.ethereum.org/EIPS/eip-4844",
    },
    {
        "statement": (
            "Account abstraction through ERC-4337 will allow smart contract wallets "
            "without consensus-layer changes, enabling gas sponsorship and social recovery"
        ),
        "source": "ERC-4337 proposal co-authored by Buterin et al, 2021",
        "category": "technical_roadmap",
        "date": "2021-09-29",
        "outcome_score": 1.0,
        "outcome_detail": (
            "ERC-4337 deployed to Ethereum mainnet on March 1, 2023. Smart contract "
            "wallets with bundled operations, gas sponsorship, and social recovery are "
            "now operational. Adopted by major wallets and dApps."
        ),
        "evidence": "ERC-4337 mainnet deployment March 2023",
        "bias": 0.1,
        "source_type": "official",
        "source_url": "https://eips.ethereum.org/EIPS/eip-4337",
    },

    # ─── FINANCIAL TRANSPARENCY ───
    {
        "statement": (
            "I haven't sold ETH for personal gain since 2018. If you see 'Vitalik sends "
            "XXX ETH to exchange,' it's almost always me donating to some charity or "
            "nonprofit, and the recipient selling because they have to cover expenses"
        ),
        "source": "Public statement, multiple tweets and interviews 2023",
        "category": "financial_transparency",
        "date": "2023-09-01",
        "outcome_score": 0.9,
        "outcome_detail": (
            "On-chain analysis confirms Buterin's ETH movements have been primarily "
            "donations and project funding. His public wallet is tracked and verifiable. "
            "In 2025 he sold ~$6.6M ETH but disclosed it in advance as planned withdrawals "
            "for project funding, not personal profit. Substantially verified."
        ),
        "evidence": "Arkham Intelligence wallet tracking, on-chain records, public disclosures",
        "bias": 0.1,
        "source_type": "social_media",
        "source_url": "https://news.bitcoin.com/vitalik-buterin-i-havent-sold-eth-for-personal-gain-since-2018/",
    },
    {
        "statement": (
            "All Ethereum code should be open source. I support it only if it's open source"
        ),
        "source": "Tweet August 12, 2025 and consistent public position",
        "category": "governance",
        "date": "2021-01-01",
        "outcome_score": 1.0,
        "outcome_detail": (
            "All Ethereum clients (Geth, Nethermind, Prysm, Lighthouse, Erigon) are "
            "open source. The Ethereum protocol itself is fully open. In February 2026, "
            "Buterin committed ~$45M in ETH to open-source security and privacy projects. "
            "Consistent walk-the-talk on open source."
        ),
        "evidence": "GitHub repos, $45M open source commitment Feb 2026",
        "bias": 0.0,
        "source_type": "social_media",
        "source_url": "https://www.theblock.co/post/387804/vitalik-buterin-commits-roughly-45-million-in-eth-to-open-source-security-and-privacy-projects",
    },

    # ─── CHARITABLE COMMITMENTS ───
    {
        "statement": (
            "I am donating the SHIB and other meme tokens sent to my wallet. "
            "Over $1 billion in SHIB to India COVID-Crypto Relief Fund"
        ),
        "source": "On-chain transactions, May 12-13 2021",
        "category": "philanthropy",
        "date": "2021-05-12",
        "outcome_score": 0.85,
        "outcome_detail": (
            "Buterin transferred 50 trillion SHIB (~$1B at time of transfer) plus 500 ETH "
            "to India COVID relief. The fund eventually converted portions through Wintermute, "
            "realizing ~$464M in USDC and distributing INR 287.5 crores ($38.4M) to Indian "
            "charities. Full amount not immediately liquid due to market impact, but donation "
            "was real and substantial. He also burned 90% of remaining meme tokens."
        ),
        "evidence": "On-chain transfers, CryptoRelief fund reports, Wintermute transactions",
        "bias": 0.0,
        "source_type": "official",
        "source_url": "https://edition.cnn.com/2021/05/13/business/ethereum-shiba-inu-india-covid-donation",
    },
    {
        "statement": (
            "I will fund pandemic preparedness and biomedical research through Balvi, "
            "a new philanthropic organization focused on public goods"
        ),
        "source": "Multiple public statements and donation announcements, 2022-2023",
        "category": "philanthropy",
        "date": "2022-01-01",
        "outcome_score": 1.0,
        "outcome_detail": (
            "Balvi was established and has made substantial donations: $9.4M USDC to "
            "University of Maryland for air disinfection research (Nov 2022), $15M to "
            "UC San Diego for airborne pathogen research (2023), $10M more to CryptoRelief "
            "India. Total philanthropic giving exceeds $100M across multiple causes."
        ),
        "evidence": "Balvi donation records, university press releases",
        "bias": 0.0,
        "source_type": "official",
        "source_url": "https://thegivingblock.com/resources/vitalik-buterin-makes-historic-9-4m-usdc-donation-to-fund-medical-research/",
    },

    # ─── HONEST ABOUT DELAYS / WRONG PREDICTIONS ───
    {
        "statement": (
            "Ethereum will switch to proof of stake by end of 2017. "
            "Casper is over three-quarters complete"
        ),
        "source": "Interviews and public statements, early 2017",
        "category": "technical_roadmap",
        "date": "2017-03-01",
        "outcome_score": 0.4,
        "outcome_detail": (
            "PoS did not ship in 2017. Timeline was off by 5 years (delivered Sept 2022). "
            "However, Buterin publicly acknowledged the delays, pivoted the approach from "
            "Casper FFG to the Beacon Chain design, and was transparent about challenges. "
            "The promise was eventually delivered, but the timeline was significantly wrong."
        ),
        "evidence": "Ethereum development history, Beacon Chain launch Dec 2020, Merge Sept 2022",
        "bias": 0.1,
        "deadline": "2017-12-31",
        "source_type": "interview",
    },
    {
        "statement": (
            "Ethereum 2.0 with full sharding will provide 100,000 transactions per second "
            "on the base layer through 64 shard chains"
        ),
        "source": "Multiple presentations and blog posts, 2018-2019",
        "category": "technical_roadmap",
        "date": "2018-06-01",
        "outcome_score": 0.5,
        "outcome_detail": (
            "Full execution sharding was abandoned in favor of the rollup-centric roadmap. "
            "Buterin publicly explained the pivot in his October 2020 blog post, noting that "
            "rollups had made execution sharding less necessary. While the specific promise "
            "was not delivered as stated, Buterin was transparent about the change and the "
            "scaling goal is being achieved via a different (arguably better) path."
        ),
        "evidence": "Buterin's rollup-centric roadmap post, Ethereum Foundation roadmap updates",
        "bias": 0.1,
        "source_type": "official",
    },
    {
        "statement": (
            "The Ethereum ecosystem post-Merge will be about 55% complete. "
            "There is still significant work on scaling, security, and user experience"
        ),
        "source": "EthCC Paris talk, July 2022",
        "category": "technical_roadmap",
        "date": "2022-07-21",
        "outcome_score": 0.9,
        "outcome_detail": (
            "Honest, calibrated assessment. Post-Merge, Ethereum has continued shipping: "
            "Shanghai/Capella (staking withdrawals, April 2023), Dencun (EIP-4844, March 2024), "
            "Pectra (2025). The roadmap (Surge, Scourge, Verge, Purge, Splurge) continues. "
            "The 55% framing was appropriately humble rather than over-promising."
        ),
        "evidence": "Ethereum upgrade history, ongoing roadmap execution",
        "bias": 0.0,
        "source_type": "conference",
        "source_url": "https://fortune.com/2022/07/21/vitalik-buterin-ethereum-merge-ethcc-paris/",
    },

    # ─── GOVERNANCE / PHILOSOPHY ───
    {
        "statement": (
            "I hope the Solana community gets its fair chance to thrive. There are "
            "some smart people in Solana. The real enemy is centralization, not other chains"
        ),
        "source": "Tweet, December 2022 (post-FTX collapse)",
        "category": "governance",
        "date": "2022-12-01",
        "outcome_score": 0.9,
        "outcome_detail": (
            "Buterin has consistently maintained this non-tribal stance. In June 2023 he "
            "criticized SEC actions against Solana, saying if Ethereum wins by other chains "
            "being kicked off exchanges, 'that's not an honorable way to win.' Actions match "
            "words: no competitive attacks on other L1s."
        ),
        "evidence": "Consistent public statements 2022-2024, no competitive attacks",
        "bias": 0.0,
        "source_type": "social_media",
        "source_url": "https://cointelegraph.com/news/ethereum-founder-says-he-hopes-solana-gets-a-chance-to-thrive",
    },
    {
        "statement": (
            "We need credible neutrality in protocol governance. Ethereum should not "
            "pick winners among applications built on it"
        ),
        "source": "Blog post 'Credible Neutrality As A Guiding Principle', January 2020",
        "category": "governance",
        "date": "2020-01-01",
        "outcome_score": 0.85,
        "outcome_detail": (
            "Ethereum's core protocol has largely maintained credible neutrality. No "
            "preferential treatment for specific dApps at the protocol level. The DAO fork "
            "(2016) remains the only major exception, predating this principle. Buterin has "
            "advocated against token-voting governance as plutocratic. Minor criticism that "
            "Ethereum Foundation grant decisions aren't perfectly neutral."
        ),
        "evidence": "Ethereum governance history, protocol-level neutrality maintained",
        "bias": 0.0,
        "source_type": "blog",
        "source_url": "https://nakamoto.com/credible-neutrality/",
    },

    # ─── INTELLECTUAL HONESTY: ADMITTING MISTAKES ───
    {
        "statement": (
            "The Ethereum whitepaper predicted many applications including on-chain "
            "decentralized exchanges, prediction markets, and identity systems"
        ),
        "source": "Ethereum whitepaper, November 2013",
        "category": "technical_roadmap",
        "date": "2013-11-01",
        "outcome_score": 0.85,
        "outcome_detail": (
            "DEXs (Uniswap, etc.), prediction markets (Polymarket, Augur), and on-chain "
            "identity (ENS, Worldcoin) all exist and thrive on Ethereum. Some whitepaper "
            "predictions like on-chain file storage and decentralized DNS had limited "
            "traction. The core vision of a general-purpose programmable blockchain was "
            "substantially realized."
        ),
        "evidence": "DeFi ecosystem, ENS, Polymarket, dApp ecosystem",
        "bias": 0.1,
        "source_type": "official",
        "source_url": "https://ethereum.org/en/whitepaper/",
    },
    {
        "statement": (
            "The original rollup-centric vision of L2s and their role in Ethereum no "
            "longer makes sense. L2s have decentralized far slower than anticipated. "
            "We need a new path"
        ),
        "source": "X post, February 2026",
        "category": "governance",
        "date": "2026-02-01",
        "outcome_score": 0.9,
        "outcome_detail": (
            "This represents intellectual honesty: publicly admitting his own previous "
            "strategy needs revision. Rather than defending a failing approach, Buterin "
            "proactively called for change. This self-correction is itself a form of "
            "follow-through on his commitment to honesty over ego."
        ),
        "evidence": "Buterin X post Feb 2026, community response",
        "bias": 0.0,
        "source_type": "social_media",
        "source_url": "https://www.theblock.co/post/388285/vitalik-buterin-reevaluates-rollup-centric-roadmap",
    },

    # ─── ENDGAME VISION ───
    {
        "statement": (
            "It will take years of refinement and audits for people to be fully comfortable "
            "storing their assets in a ZK-rollup running a full EVM. But it does look "
            "increasingly clear how a realistic but bright future for scalable blockchains "
            "is likely to emerge"
        ),
        "source": "Blog post 'Endgame', December 6, 2021",
        "category": "technical_roadmap",
        "date": "2021-12-06",
        "outcome_score": 0.8,
        "outcome_detail": (
            "Calibrated prediction. ZK-rollups (zkSync Era, StarkNet, Polygon zkEVM, Scroll) "
            "launched in 2023-2024 with growing TVL. Full EVM equivalence achieved by several. "
            "The 'years of refinement' timeline was accurate. Scalable blockchain future is "
            "materializing as predicted, though still in progress."
        ),
        "evidence": "ZK-rollup launches 2023-2024, L2Beat data",
        "bias": 0.1,
        "source_type": "blog",
        "source_url": "https://vitalik.ca/general/2021/12/06/endgame.html",
    },

    # ─── STAKING WITHDRAWALS ───
    {
        "statement": (
            "Staked ETH withdrawals will be enabled in the Shanghai/Capella upgrade, "
            "allowing validators to withdraw their staked ETH and rewards"
        ),
        "source": "Ethereum Foundation roadmap communications, 2022-2023",
        "category": "technical_roadmap",
        "date": "2022-09-20",
        "outcome_score": 1.0,
        "outcome_detail": (
            "Shanghai/Capella upgrade executed successfully on April 12, 2023. Staking "
            "withdrawals enabled as promised. No mass exodus of staked ETH occurred, "
            "contrary to fears. The upgrade went smoothly."
        ),
        "evidence": "Shanghai/Capella upgrade April 12 2023, staking withdrawal data",
        "bias": 0.1,
        "source_type": "official",
    },
]

# ──────────────────────────────────────────────────────────────────────

print("=" * 70)
print("SAY/DO POC: Vitalik Buterin Credibility Index")
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
print("\nPHASE 4: Contradictions (should be few/low)")
print("=" * 70)
contradictions = engine.get_entity_contradictions(ENTITY, min_score=0.0)
if contradictions:
    for i, c in enumerate(contradictions[:10], 1):
        print(f"  {i}. [score={c['score']:.3f}] {c['summary'][:100]}")
else:
    print("  No contradictions found (expected for high-credibility entity)")

# Phase 5: Predictions
print("\nPHASE 5: Follow-Through Predictions (new claims)")
print("=" * 70)
from omega.saydo.prediction import predict_followthrough

test_statements = [
    ("Verkle trees will be implemented in Ethereum within 2 years", "technical_roadmap"),
    ("I will continue to donate to public goods and open source", "philanthropy"),
    ("Ethereum will achieve 100,000 TPS through L2 scaling", "technical_roadmap"),
    ("The Ethereum Foundation should be more transparent about spending", "governance"),
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
    if cred > 0.75:
        print(f"  PASS: Credibility score {cred:.3f} > 0.75 threshold")
    else:
        print(f"  FAIL: Credibility score {cred:.3f} <= 0.75 threshold")
        print(f"  The credibility system may need tuning.")
else:
    print("  WARN: No credibility score computed")

ftr = profile.get("follow_through_rate", 0.0)
if ftr > 0.75:
    print(f"  PASS: Follow-through rate {ftr:.0%} > 75%")
else:
    print(f"  WARN: Follow-through rate {ftr:.0%} <= 75%")

print(f"\n  Contradiction score: {profile['contradiction_score']:.3f}")
print(f"  Total kept: {profile['outcomes_followed']}/{profile['total_statements']}")

print("\n" + "=" * 70)
print("POC COMPLETE")
print("=" * 70)
