#!/usr/bin/env python3
"""Say/Do POC: Anatoly Yakovenko (Solana) Credibility Index.

Populates the Say/Do engine with Anatoly Yakovenko's public statements
and their known outcomes, then generates the full credibility profile.

Validation target: ~0.52 credibility. Genuine builder who stayed through
Solana's darkest period (FTX collapse, outages, 96% price crash). Makes
ambitious claims that often fall short in the near term. Sometimes
minimizes problems but later acknowledges them honestly.

All statements sourced from public record (tweets, podcasts, conference
talks, interviews).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omega.sqlite_store import SQLiteStore
from omega.saydo.engine import get_saydo_engine, _engine_instance
import omega.saydo.engine as eng_mod
import omega.bridge as bridge

DB_PATH = Path(__file__).parent.parent / "data" / "poc_saydo_anatoly.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

if DB_PATH.exists():
    DB_PATH.unlink()

store = SQLiteStore(db_path=str(DB_PATH))
bridge._store_instance = store
eng_mod._engine_instance = None

engine = get_saydo_engine()

ENTITY = "Anatoly Yakovenko"
ENTITY_TYPE = "person"

DATA = [
    # --- PERFORMANCE CLAIMS ---
    {
        "statement": (
            "We benchmarked at about 50,000 TPS with peaks of 65,000. "
            "Benchmarking is a game"
        ),
        "source": "Acquired Podcast interview, 2022",
        "category": "performance",
        "date": "2022-06-01",
        "outcome_score": 0.3,
        "outcome_detail": (
            "Solana's theoretical peak of 65,000 TPS has never been achieved in "
            "real-world production. Actual mainnet throughput averages 1,000-4,000 TPS "
            "(excluding vote transactions, real user TPS closer to ~1,050). The 65K "
            "figure was a lab benchmark. In August 2025, Solana hit 107,664 TPS in a "
            "synthetic stress test (mostly no-op instructions). Gap between claim "
            "and reality is enormous, though he did caveat 'benchmarking is a game.'"
        ),
        "evidence": "Mainnet TPS data (~1-4K real), 65K lab benchmark, Aug 2025 stress test",
        "bias": 0.6,
        "source_type": "interview",
    },
    {
        "statement": (
            "The goal of Solana is to carry transactions as fast as news travels "
            "around the world, speed of light through fiber. Who we're competing "
            "with is NASDAQ and the New York Stock Exchange"
        ),
        "source": "UDC 2021 developer conference and Acquired podcast",
        "category": "performance",
        "date": "2021-06-01",
        "outcome_score": 0.3,
        "outcome_detail": (
            "NASDAQ processes roughly 250,000-600,000 messages/sec with sub-millisecond "
            "latency in a centralized, co-located environment. Solana at ~1,000-4,000 "
            "real-world TPS with 400ms block times is orders of magnitude slower. Even "
            "Firedancer's 1.1M TPS synthetic benchmark was a burst test with disabled "
            "limits. The comparison remains aspirational, not realized. However, Solana "
            "is the closest any public blockchain has come, and on-chain order books "
            "(Phoenix) do function."
        ),
        "evidence": "NASDAQ throughput data, Solana mainnet TPS, Firedancer benchmarks",
        "bias": 0.6,
        "source_type": "conference",
    },

    # --- RELIABILITY / HONESTY ---
    {
        "statement": (
            "We've had a lot of challenges over the last year. This whole last year "
            "has been all about reliability"
        ),
        "source": "Solana Breakpoint 2022 keynote, Lisbon, November 5, 2022",
        "category": "reliability",
        "date": "2022-11-05",
        "outcome_score": 0.8,
        "outcome_detail": (
            "Honest, public acknowledgment at Solana's flagship conference. In 2022, "
            "Solana suffered 26 documented issues ranging from degraded performance to "
            "full outages, with approximately 4 days and 12 hours of total downtime. He "
            "admitted block times degraded to '15 to 20 seconds' when they should be "
            "400ms, saying 'that's not the experience we want to deliver.' Credit for "
            "transparency at own conference."
        ),
        "evidence": "Breakpoint 2022 keynote, Solana outage tracker (26 incidents in 2022)",
        "bias": 0.2,
        "source_type": "conference",
    },
    {
        "statement": "lol",
        "source": "Twitter/X, January 2022 (during Solana's 6th outage that month)",
        "category": "reliability",
        "date": "2022-01-22",
        "outcome_score": 0.2,
        "outcome_detail": (
            "Tweeted 'lol' alongside a screenshot showing 2.05 million duplicate data "
            "packets on a Solana node during the sixth serious outage that month (8+ hours "
            "of downtime over a weekend). SOL had lost 35% in seven days. Traders had "
            "funds locked in DeFi protocols. Dismissive response covered by Fortune and "
            "Bloomberg as tone-deaf crisis communication."
        ),
        "evidence": "Fortune coverage Jan 2022, Bloomberg, SOL price data",
        "bias": 0.7,
        "source_type": "social_media",
    },
    {
        "statement": (
            "I don't know if the network will go down again. It doesn't really "
            "matter though. As long as there's at least one copy of the ledger, "
            "the funds are still safe"
        ),
        "source": "Interview at Solana Breakpoint 2021",
        "category": "reliability",
        "date": "2021-11-01",
        "outcome_score": 0.25,
        "outcome_detail": (
            "Network went down repeatedly throughout 2022 (26 incidents). While fund "
            "safety claim was technically correct (no funds permanently lost), the "
            "statement badly underestimated impact on DeFi users facing liquidations, "
            "traders unable to exit positions, and NFT minters losing opportunities. "
            "It very much 'mattered' to users even if funds were safe."
        ),
        "evidence": "2022 outage history (26 incidents), user impact reports",
        "bias": 0.7,
        "source_type": "interview",
    },
    {
        "statement": (
            "The number one priority is safety. Then it's liveness"
        ),
        "source": "Interviews discussing Solana outages, 2022",
        "category": "reliability",
        "date": "2022-06-01",
        "outcome_score": 0.8,
        "outcome_detail": (
            "This philosophy was consistently followed. When Solana went down, it was "
            "always because the network halted to prevent invalid state (safety over "
            "liveness). No funds were ever lost due to an outage. Feb 2023 outage lasted "
            "~19 hours because validators chose to restart cleanly rather than risk state "
            "corruption. This principle was genuinely upheld even when painful."
        ),
        "evidence": "Zero fund losses across 26+ outages, validator restart procedures",
        "bias": 0.2,
        "source_type": "interview",
    },

    # --- NETWORK FIXES ---
    {
        "statement": (
            "Local fee markets mean plenty of resources to add transactions from "
            "other accounts elsewhere on the network, without any impact on fees"
        ),
        "source": "Twitter thread, reported by Decrypt, June 16, 2022",
        "category": "technical",
        "date": "2022-06-16",
        "outcome_score": 0.35,
        "outcome_detail": (
            "Concept was sound but implementation took years and was incomplete. Local "
            "fee markets introduced but don't work deterministically under high load. "
            "Yakovenko later acknowledged 'queues back up during high load and "
            "prioritization can't occur in those queues until reaching the scheduler.' "
            "During 2024 memecoin mania, up to 75% of transactions failed, contradicting "
            "the promise. Fixes (SIMD-0110, Agave v1.18 scheduler) came in 2024."
        ),
        "evidence": "2024 memecoin congestion (75% tx failure), SIMD-0110, Agave v1.18",
        "bias": 0.55,
        "source_type": "social_media",
    },
    {
        "statement": (
            "QUIC protocol upgrade replaces UDP with authenticated, congestion-aware "
            "connections plus stake-weighted QoS to prevent spam"
        ),
        "source": "U.Today report on GitHub/Twitter, May 2022",
        "category": "technical",
        "date": "2022-05-01",
        "outcome_score": 0.75,
        "outcome_detail": (
            "QUIC was a major improvement. Replaced vulnerable UDP with authenticated, "
            "congestion-aware connections. Combined with stake-weighted QoS. Measurably "
            "improved network resilience: Solana went nearly a full year without a major "
            "outage (Feb 2023 to Feb 2024). In February 2026, survived a 6 Tbps DDoS "
            "attack without downtime. Not a silver bullet but genuine improvement."
        ),
        "evidence": "QUIC deployment, year without major outage, 6 Tbps DDoS survival Feb 2026",
        "bias": 0.3,
        "source_type": "official",
    },

    # --- FTX / RESILIENCE ---
    {
        "statement": (
            "The rest of the developers building on Solana really had nothing to do "
            "with FTX. We had over 800 projects submitted in the last hackathon, "
            "two months after the FTX collapse"
        ),
        "source": "CoinDesk interview, May 4, 2023",
        "category": "ecosystem",
        "date": "2023-05-04",
        "outcome_score": 0.85,
        "outcome_detail": (
            "Largely vindicated. While Solana's price crashed 96% ($260 to $8) due to "
            "FTX ties, the developer ecosystem proved resilient. SOL became the best- "
            "performing major crypto in 2023, up over 500%. Hackathon claim was verifiable "
            "and true. FTX collapse was a financial contagion event, not a technical "
            "indictment. Yakovenko stayed and built while many would have fled."
        ),
        "evidence": "SOL price recovery (500%+ in 2023), hackathon data, developer metrics",
        "bias": 0.3,
        "source_type": "interview",
    },
    {
        "statement": (
            "Execution is the only moat. The only reason a competitor would win over "
            "Solana is that they execute faster, overcoming network effects"
        ),
        "source": "Blockworks Lightspeed podcast with Mert Mumtaz, 2024",
        "category": "strategy",
        "date": "2024-03-01",
        "outcome_score": 0.8,
        "outcome_detail": (
            "Validated by Solana's trajectory. Despite catastrophic events (FTX collapse, "
            "repeated outages, 'beta' criticism), continued shipping velocity brought "
            "Solana back to #4-5 crypto by market cap. DeFi TVL recovered, NFT volume "
            "grew, new use cases (memecoins, DePIN, Blinks) emerged. Showed intellectual "
            "humility: acknowledged Solana could be displaced by better execution."
        ),
        "evidence": "Solana recovery to top-5 crypto, DeFi TVL growth, ecosystem expansion",
        "bias": 0.2,
        "source_type": "interview",
    },

    # --- FIREDANCER ---
    {
        "statement": (
            "There is a 50% chance that Firedancer will go live on mainnet before "
            "the Solana Breakpoint conference in September 2024"
        ),
        "source": "The Defiant interview, May 2024",
        "category": "product_delivery",
        "date": "2024-05-01",
        "outcome_score": 0.45,
        "outcome_detail": (
            "Firedancer did NOT go live on mainnet before Breakpoint 2024. Intermediate "
            "'Frankendancer' (hybrid) launched with early adopters in September 2024. "
            "Full Firedancer launched on mainnet approximately December 2025, 15+ months "
            "after the stated 50% probability window. He hedged it as '50%' which was "
            "honest framing for a hard engineering problem."
        ),
        "evidence": "Frankendancer Sep 2024, full Firedancer ~Dec 2025",
        "bias": 0.35,
        "source_type": "interview",
    },
    {
        "statement": (
            "Folks can stop calling it beta at any time, it's just my personal "
            "preference that we do that after Firedancer ships"
        ),
        "source": "Solana Crossroads 2024 conference",
        "category": "product_delivery",
        "date": "2024-04-01",
        "outcome_score": 0.6,
        "outcome_detail": (
            "Solana was in 'mainnet beta' for years, which critics called a convenient "
            "excuse for outages. Yakovenko tied removal of 'beta' to Firedancer's launch, "
            "acknowledging single-client risk was a legitimate weakness. Firedancer "
            "eventually launched late 2025. The 'beta' label was both honest (single-client "
            "risk is real) and convenient (excused years of outages)."
        ),
        "evidence": "Firedancer mainnet launch ~Dec 2025, prior 'beta' designation history",
        "bias": 0.4,
        "source_type": "conference",
    },

    # --- SAGA PHONE ---
    {
        "statement": (
            "Our goal isn't to sell 10 million units. We would be very happy with "
            "25,000 to 50,000 units sold in the next year"
        ),
        "source": "TechCrunch Disrupt 2022, October 19, 2022",
        "category": "product_delivery",
        "date": "2022-10-19",
        "outcome_score": 0.4,
        "outcome_detail": (
            "Initial sales catastrophic: only ~2,500 units in first 6+ months (5-10% of "
            "target). Then dramatic twist: BONK memecoin airdropped 30M tokens to Saga "
            "owners, making the phone profitable by itself. Sales surged past 150,000 units "
            "and device sold out. Final outcome exceeded target but entirely due to memecoin "
            "speculation, not the intended developer-platform use case."
        ),
        "evidence": "Initial 2,500 sales, BONK airdrop, 150K+ final sales",
        "bias": 0.3,
        "source_type": "conference",
    },
    {
        "statement": (
            "I hope it's not a money pit. We'd need to sell over 250,000 units "
            "annually to break even, without accounting for engineering costs"
        ),
        "source": "TechCrunch Chain Reaction podcast, January 25, 2024",
        "category": "product_delivery",
        "date": "2024-01-25",
        "outcome_score": 0.7,
        "outcome_detail": (
            "Remarkably candid admission for a CEO. Saga team had only about 10 people. "
            "Breakeven target of 250K/year was never achieved through organic phone sales. "
            "Chapter 2/Seeker successor hit 150,000+ preorders generating ~$67M. Solana "
            "Mobile remains a subsidized bet. Honest economics assessment."
        ),
        "evidence": "Saga team size, 150K+ Seeker preorders, $67M revenue",
        "bias": 0.15,
        "source_type": "interview",
    },

    # --- MEMECOIN STANCE ---
    {
        "statement": (
            "Blessed are the memecoin traders, for those who can overcome their spam "
            "will inherit the metaverse. Meme coin trading is bizarre but it's "
            "provided a welcome stress test"
        ),
        "source": "CoinDesk interview March 2024, Emergence conference Prague late 2024",
        "category": "ecosystem",
        "date": "2024-03-20",
        "outcome_score": 0.5,
        "outcome_detail": (
            "During March 2024 memecoin mania, Solana experienced severe congestion with "
            "large percentage of transactions failing. Yakovenko framed as positive stress "
            "test. Partially justified: congestion exposed scheduler bugs and fee market "
            "weaknesses that led to real fixes (Agave v1.18). But for users who lost "
            "money on failed transactions during this period, 'welcome stress test' was "
            "cold comfort."
        ),
        "evidence": "March 2024 congestion, high tx failure rate, subsequent Agave v1.18 fixes",
        "bias": 0.55,
        "source_type": "interview",
    },

    # --- MATURITY / NON-TRIBALISM ---
    {
        "statement": (
            "Don't bring back the Ethereum killer narrative. It is lame. I don't "
            "anticipate a future in which Solana thrives while Ethereum dies"
        ),
        "source": "Twitter/X and interviews, December 2023",
        "category": "strategy",
        "date": "2023-12-01",
        "outcome_score": 0.75,
        "outcome_detail": (
            "Showed maturity and strategic intelligence. De-escalated tribalism rather "
            "than feeding it. The 'Ethereum killer' framing was never accurate since "
            "both chains serve different use cases. His Pareto efficiency argument (both "
            "can win) has been borne out as both ecosystems grew in 2024-2025."
        ),
        "evidence": "Both Solana and Ethereum ecosystem growth 2024-2025",
        "bias": 0.15,
        "source_type": "social_media",
    },
]

# ──────────────────────────────────────────────────────────────────────

print("=" * 70)
print("SAY/DO POC: Anatoly Yakovenko (Solana) Credibility Index")
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
    ("Solana will achieve sustained 10,000+ TPS on mainnet in 2026", "performance"),
    ("Firedancer will improve Solana reliability to 99.9% uptime", "reliability"),
    ("Solana will process more daily transactions than Ethereum L1 in 2026", "ecosystem"),
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
    if 0.35 <= cred <= 0.65:
        print(f"  PASS: Credibility score {cred:.3f} in target range [0.35, 0.65]")
    else:
        print(f"  NOTE: Credibility score {cred:.3f} outside target range [0.35, 0.65]")
else:
    print("  WARN: No credibility score computed")

print(f"\n  Contradiction score: {profile['contradiction_score']:.3f}")
print(f"  Total kept: {profile['outcomes_followed']}/{profile['total_statements']}")

print("\n" + "=" * 70)
print("POC COMPLETE")
print("=" * 70)
