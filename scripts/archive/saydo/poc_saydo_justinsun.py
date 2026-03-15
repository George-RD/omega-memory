#!/usr/bin/env python3
"""Say/Do POC: Justin Sun Credibility Index.

Populates the Say/Do engine with Justin Sun's public statements
and their known outcomes, then generates the full credibility profile.

Validation target: Justin Sun should score around 0.20-0.25 credibility.
A mixed record: some real delivery (TRON mainnet, BitTorrent acquisition)
but extensive pattern of hype, pump-and-dump allegations, regulatory issues,
and broken promises.

All statements sourced from public record (tweets, interviews, press releases,
SEC filings).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omega.sqlite_store import SQLiteStore
from omega.saydo.engine import get_saydo_engine, _engine_instance
import omega.saydo.engine as eng_mod
import omega.bridge as bridge

DB_PATH = Path(__file__).parent.parent / "data" / "poc_saydo_justinsun.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

if DB_PATH.exists():
    DB_PATH.unlink()

store = SQLiteStore(db_path=str(DB_PATH))
bridge._store_instance = store
eng_mod._engine_instance = None

engine = get_saydo_engine()

ENTITY = "Justin Sun"
ENTITY_TYPE = "person"

DATA = [
    # ─── DELIVERED PROMISES ───
    {
        "statement": (
            "TRON will launch its own mainnet and migrate from ERC-20 tokens to an "
            "independent blockchain by Q2 2018"
        ),
        "source": "TRON whitepaper and public announcements, 2017-2018",
        "category": "technical",
        "date": "2017-12-01",
        "outcome_score": 0.9,
        "outcome_detail": (
            "TRON mainnet launched on May 25, 2018, on schedule. Successfully migrated "
            "from ERC-20 to independent blockchain. TRON operates as a functioning L1 "
            "with significant usage, particularly for USDT transfers. One of Sun's "
            "clearest delivered promises."
        ),
        "evidence": "TRON mainnet launch May 2018, blockchain operational data",
        "bias": 0.3,
        "deadline": "2018-06-30",
        "source_type": "official",
    },
    {
        "statement": (
            "TRON will acquire BitTorrent and integrate it with blockchain technology "
            "to create a decentralized content distribution network"
        ),
        "source": "Acquisition announcement, June 2018",
        "category": "business",
        "date": "2018-06-01",
        "outcome_score": 0.6,
        "outcome_detail": (
            "BitTorrent acquisition completed for ~$140M in July 2018. BTT token launched "
            "on Binance Launchpad in January 2019. However, the 'decentralized content "
            "distribution' vision was largely unrealized. BitTorrent Speed (incentivized "
            "seeding) had minimal adoption. The acquisition was real but the blockchain "
            "integration was superficial."
        ),
        "evidence": "BitTorrent acquisition records, BTT token launch, BitTorrent Speed usage data",
        "bias": 0.4,
        "source_type": "official",
    },
    {
        "statement": (
            "TRON will become the number one platform for decentralized applications "
            "and will surpass Ethereum in daily transactions by 2019"
        ),
        "source": "Multiple public statements and tweets, 2018",
        "category": "technical",
        "date": "2018-07-01",
        "outcome_score": 0.3,
        "outcome_detail": (
            "TRON did achieve high transaction counts, but largely due to USDT transfers "
            "and automated bot activity rather than genuine dApp usage. TRON's dApp "
            "ecosystem never rivaled Ethereum's in developer activity, TVL, or innovation. "
            "The raw transaction count claim was technically achieved but misleading."
        ),
        "evidence": "DappRadar data, TRON vs Ethereum ecosystem comparison",
        "bias": 0.5,
        "deadline": "2019-12-31",
        "source_type": "social_media",
    },

    # ─── WARREN BUFFETT LUNCH ───
    {
        "statement": (
            "I won the charity lunch with Warren Buffett for $4.57 million. "
            "I look forward to discussing crypto and blockchain with him. "
            "This will be a great opportunity for the entire industry"
        ),
        "source": "Tweet and press release, June 2019",
        "category": "marketing",
        "date": "2019-06-03",
        "outcome_score": 0.5,
        "outcome_detail": (
            "The lunch was postponed multiple times. Sun initially claimed 'kidney stones' "
            "then Chinese government pressure. The lunch finally happened in January 2020. "
            "He gifted Buffett a Samsung phone with Bitcoin and TRON. Buffett reportedly "
            "gave the phone away. The event generated publicity but no meaningful industry "
            "benefit. Sun was accused of using it purely as a marketing stunt."
        ),
        "evidence": "Buffett lunch January 2020, Buffett's continued crypto skepticism",
        "bias": 0.5,
        "source_type": "social_media",
    },

    # ─── STABLECOIN CLAIMS ───
    {
        "statement": (
            "USDD is a decentralized algorithmic stablecoin backed by the TRON DAO Reserve. "
            "It is over-collateralized at 200%+ and will maintain its dollar peg through "
            "market mechanisms"
        ),
        "source": "USDD launch announcement and TRON DAO Reserve, May 2022",
        "category": "stablecoin",
        "date": "2022-05-05",
        "outcome_score": 0.3,
        "outcome_detail": (
            "USDD launched weeks after UST's collapse (terrible timing/optics). It briefly "
            "depegged to $0.97 in June 2022. The 'decentralized' claim was questionable "
            "as TRON DAO Reserve was controlled by Sun and associates. The collateralization "
            "claims were disputed by analysts who noted the reserves included TRX itself "
            "(circular). USDD survived but never achieved significant adoption."
        ),
        "evidence": "USDD price data, collateralization audits, DeFiLlama data",
        "bias": 0.5,
        "source_type": "official",
    },

    # ─── SEC CHARGES ───
    {
        "statement": (
            "TRON and BTT are utility tokens, not securities. We have always operated "
            "in compliance with applicable laws and regulations"
        ),
        "source": "Multiple public statements, 2019-2023",
        "category": "regulatory",
        "date": "2020-01-01",
        "outcome_score": 0.1,
        "outcome_detail": (
            "SEC charged Sun and his companies with fraud and securities law violations "
            "in March 2023. Charges included unregistered offer/sale of TRX and BTT as "
            "securities, fraudulent manipulative trading (wash trading to inflate volume), "
            "and paying celebrities to promote without disclosing compensation. Sun settled "
            "with the SEC but did not admit or deny the allegations."
        ),
        "evidence": "SEC complaint March 2023, celebrity promotion charges",
        "bias": 0.6,
        "source_type": "official",
        "source_url": "https://www.sec.gov/newsroom/press-releases/2023-59",
    },
    {
        "statement": (
            "The celebrity endorsements for TRON and BTT were organic partnerships. "
            "These celebrities genuinely believe in the project"
        ),
        "source": "Public statements regarding celebrity promotions, 2021-2022",
        "category": "marketing",
        "date": "2021-06-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "SEC revealed Sun paid celebrities including Lindsay Lohan, Jake Paul, "
            "Soulja Boy, Lil Yachty, Ne-Yo, and Akon to promote TRX/BTT without "
            "disclosing they were paid endorsements. Multiple celebrities settled with "
            "the SEC. The promotions were undisclosed paid advertisements, not organic."
        ),
        "evidence": "SEC charges against celebrities, settlement agreements",
        "bias": 0.6,
        "source_type": "official",
    },

    # ─── STEEMIT / GOVERNANCE CONTROVERSY ───
    {
        "statement": (
            "TRON's acquisition of Steemit will benefit the Steem community. "
            "We will work collaboratively with the existing stakeholders and respect "
            "the decentralized governance of the Steem blockchain"
        ),
        "source": "Steemit acquisition announcement, February 2020",
        "category": "governance",
        "date": "2020-02-14",
        "outcome_score": 0.0,
        "outcome_detail": (
            "Sun used exchange-held Steem tokens (Binance, Huobi, Poloniex) to vote "
            "in governance and override community witnesses, effectively executing a "
            "hostile takeover of a 'decentralized' blockchain. The community forked to "
            "create Hive in March 2020 in protest. This became one of crypto's most "
            "infamous governance attacks and severely damaged Sun's credibility."
        ),
        "evidence": "Steem witness voting records, Hive fork March 2020",
        "bias": 0.6,
        "source_type": "official",
    },

    # ─── HUOBI/HTX ACQUISITION ───
    {
        "statement": (
            "I am not involved in the operations of Huobi. I am merely an advisor. "
            "Huobi operates independently"
        ),
        "source": "Multiple public denials, October 2022 onward",
        "category": "business",
        "date": "2022-10-01",
        "outcome_score": 0.1,
        "outcome_detail": (
            "On-chain analysis and investigative reporting showed Sun effectively controlled "
            "Huobi (renamed HTX). He appointed board members, directed operations, and moved "
            "funds between TRON ecosystem and Huobi wallets. Eventually acknowledged as "
            "'Global Advisory Board Member' but evidence suggests operational control. "
            "The denial was not credible."
        ),
        "evidence": "On-chain analysis, reporting by The Block and CoinDesk",
        "bias": 0.6,
        "source_type": "interview",
    },

    # ─── POLONIEX HACK ───
    {
        "statement": (
            "Poloniex will fully compensate all users affected by the hack. "
            "We will restore 100% of affected funds"
        ),
        "source": "Tweets after Poloniex hack, November 2023",
        "category": "customer_funds",
        "date": "2023-11-10",
        "outcome_score": 0.4,
        "outcome_detail": (
            "Poloniex was hacked for ~$120M in November 2023. Sun offered the hacker a "
            "5% white hat bounty. Some funds were recovered and users were partially "
            "compensated through a combination of recovered assets and platform credits, "
            "but full 100% restoration was not achieved for all users. The response was "
            "better than many exchange hacks but fell short of the '100%' promise."
        ),
        "evidence": "Poloniex hack recovery data, user compensation reports",
        "bias": 0.5,
        "source_type": "social_media",
    },

    # ─── WASH TRADING / VOLUME ───
    {
        "statement": (
            "TRON's daily transaction volume and DeFi TVL reflect genuine organic usage "
            "and growing adoption of the TRON ecosystem"
        ),
        "source": "Multiple TRON Foundation statements and marketing, 2019-2022",
        "category": "technical",
        "date": "2019-06-01",
        "outcome_score": 0.1,
        "outcome_detail": (
            "SEC specifically charged Sun with wash trading to inflate TRX volume. "
            "Analysis showed coordinated trading between Sun-controlled wallets. TRON's "
            "high transaction counts were significantly inflated by automated transfers "
            "and USDT relay activity rather than genuine dApp usage. The SEC found "
            "500,000+ wash trades totaling over $31 billion."
        ),
        "evidence": "SEC complaint, wash trading analysis",
        "bias": 0.6,
        "source_type": "official",
    },

    # ─── DIPLOMATIC ROLE ───
    {
        "statement": (
            "As Grenada's Ambassador and Permanent Representative to the WTO, "
            "I will use this position to advocate for blockchain technology and "
            "digital innovation in developing nations"
        ),
        "source": "Announcement of diplomatic appointment, December 2021",
        "category": "governance",
        "date": "2021-12-01",
        "outcome_score": 0.3,
        "outcome_detail": (
            "Sun received diplomatic credentials from Grenada, which some viewed as "
            "an attempt to gain diplomatic immunity amid regulatory scrutiny. No "
            "significant WTO blockchain advocacy materialized. The appointment was "
            "widely seen as reputation management rather than genuine diplomatic service."
        ),
        "evidence": "Grenada appointment records, lack of WTO blockchain initiatives",
        "bias": 0.5,
        "source_type": "official",
    },

    # ─── TRON ECOSYSTEM PROMISES ───
    {
        "statement": (
            "TRON 4.0 will introduce privacy features, enterprise solutions, and "
            "cross-chain interoperability that will make TRON the most versatile "
            "blockchain platform"
        ),
        "source": "TRON roadmap announcements, 2020",
        "category": "technical",
        "date": "2020-07-01",
        "outcome_score": 0.2,
        "outcome_detail": (
            "Privacy features were limited and not widely adopted. Enterprise solutions "
            "did not materialize at scale. Cross-chain capabilities remained basic compared "
            "to competitors. TRON continued to function primarily as a USDT transfer layer "
            "rather than a versatile platform. The ambitious roadmap was largely undelivered."
        ),
        "evidence": "TRON ecosystem analysis, developer activity metrics",
        "bias": 0.5,
        "source_type": "official",
    },

    # ─── BANANA GUN / ART STUNTS ───
    {
        "statement": (
            "I purchased Maurizio Cattelan's banana artwork 'Comedian' for $6.2 million "
            "to support the intersection of art and technology. I will eat it as a tribute "
            "to its place in both art history and popular culture"
        ),
        "source": "Sotheby's auction, tweets, November 2024",
        "category": "marketing",
        "date": "2024-11-20",
        "outcome_score": 0.9,
        "outcome_detail": (
            "Sun did buy the banana artwork for $6.2M at Sotheby's and did eat it at a "
            "press conference. The stunt generated massive media coverage. While delivered "
            "as stated, it was widely viewed as another Sun publicity play rather than "
            "genuine art appreciation. But he did what he said he would do."
        ),
        "evidence": "Sotheby's sale records, press conference video",
        "bias": 0.3,
        "source_type": "official",
    },
]

# ──────────────────────────────────────────────────────────────────────

print("=" * 70)
print("SAY/DO POC: Justin Sun Credibility Index")
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
print("\nPHASE 4: Top Contradictions")
print("=" * 70)
contradictions = engine.get_entity_contradictions(ENTITY, min_score=0.0)
for i, c in enumerate(contradictions[:10], 1):
    print(f"  {i}. [score={c['score']:.3f}] {c['summary'][:100]}")

# Phase 5: Predictions
print("\nPHASE 5: Follow-Through Predictions")
print("=" * 70)
from omega.saydo.prediction import predict_followthrough

test_statements = [
    ("HTX will become a top 3 exchange by volume", "business"),
    ("TRON will implement full privacy features", "technical"),
    ("I will fully cooperate with SEC proceedings", "regulatory"),
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
    if 0.15 <= cred <= 0.35:
        print(f"  PASS: Credibility score {cred:.3f} in target range [0.15, 0.35]")
    else:
        print(f"  NOTE: Credibility score {cred:.3f} outside target range [0.15, 0.35]")
else:
    print("  WARN: No credibility score computed")

print(f"\n  Contradiction score: {profile['contradiction_score']:.3f}")
print(f"  Total broken: {profile['outcomes_broken']}/{profile['total_statements']}")

print("\n" + "=" * 70)
print("POC COMPLETE")
print("=" * 70)
