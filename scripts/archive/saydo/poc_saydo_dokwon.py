#!/usr/bin/env python3
"""Say/Do POC: Do Kwon Credibility Index.

Populates the Say/Do engine with Do Kwon's well-documented public statements
and their known outcomes, then generates the full credibility profile.

Validation anchor: Do Kwon should score BELOW 0.15 credibility.
If he doesn't, something is broken in the credibility system.

All statements sourced from public record (tweets, interviews, court filings).
Uses the new credibility features: specificity, bias, partial outcomes,
deadlines, source_url, source_type.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omega.sqlite_store import SQLiteStore
from omega.saydo.engine import get_saydo_engine, _engine_instance
import omega.saydo.engine as eng_mod
import omega.bridge as bridge

DB_PATH = Path(__file__).parent.parent / "data" / "poc_saydo_dokwon.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Fresh DB each run for reproducibility
if DB_PATH.exists():
    DB_PATH.unlink()

store = SQLiteStore(db_path=str(DB_PATH))
bridge._store_instance = store
eng_mod._engine_instance = None

engine = get_saydo_engine()

ENTITY = "Do Kwon"
ENTITY_TYPE = "person"

# ──────────────────────────────────────────────────────────────────────
# STATEMENTS + OUTCOMES
# Each dict has: statement, source, category, date, followed_through,
# outcome_detail, evidence, and new credibility fields:
# bias, deadline, source_url, source_type, outcome_score
# ──────────────────────────────────────────────────────────────────────

DATA = [
    # ─── STABLECOIN / UST CLAIMS ───
    {
        "statement": "UST algorithmic mechanism allows it to self-heal and automatically maintain its dollar peg",
        "source": "Multiple public statements, SEC trial evidence",
        "category": "stablecoin",
        "date": "2021-06-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "May 2021 depeg was secretly fixed by Jump Trading buying millions in UST, "
            "not the algorithm. Kwon hid Jump's involvement and presented the repeg as "
            "proof the algorithm worked. SEC proved this was deliberate fraud."
        ),
        "evidence": "SEC complaint, Jump Trading whistleblower testimony, April 2024 jury verdict",
        "bias": 0.5,  # Direct financial interest in promoting UST
        "source_type": "official",
        "source_url": "https://www.sec.gov/newsroom/press-releases/2023-32",
    },
    {
        "statement": "By my hand $DAI will die",
        "source": "Tweet @stablekwon, March 23 2022",
        "category": "stablecoin",
        "date": "2022-03-23",
        "outcome_score": 0.0,
        "outcome_detail": (
            "UST depegged and went to near-zero on May 9-12, 2022. DAI maintained its "
            "peg throughout the crisis and remains operational in 2026 as one of the "
            "largest decentralized stablecoins."
        ),
        "evidence": "DAI price data, MakerDAO operations",
        "bias": 0.4,
        "source_type": "social_media",
        "source_url": "https://x.com/stablekwon/status/1506494471873081352",
    },
    {
        "statement": "Men will literally attack a stablecoin unsuccessfully instead of going to therapy",
        "source": "Tweet @stablekwon (since deleted)",
        "category": "stablecoin",
        "date": "2022-01-15",
        "outcome_score": 0.0,
        "outcome_detail": (
            "The 'unsuccessful' attack he mocked was a dress rehearsal. The May 2022 "
            "coordinated sell pressure destroyed UST entirely, wiping out $40 billion."
        ),
        "evidence": "UST price history, post-mortem analyses",
        "bias": 0.4,
        "source_type": "social_media",
    },
    {
        "statement": (
            "Anon, you could listen to CT influensooors about UST depegging for the 69th time. "
            "Or you could remember they're all now poor, and go for a run instead"
        ),
        "source": "Tweet @stablekwon, May 7 2022",
        "category": "stablecoin",
        "date": "2022-05-07",
        "outcome_score": 0.0,
        "outcome_detail": (
            "Posted on day one of the depeg. Within 4 days UST fell to $0.06 and LUNA "
            "went from ~$80 to fractions of a penny. $40B wiped out. The critics he "
            "called 'poor' were proven correct."
        ),
        "evidence": "UST/LUNA price data, May 7-12 2022",
        "bias": 0.5,
        "source_type": "social_media",
        "source_url": "https://x.com/stablekwon/status/1523075465384136704",
    },
    {
        "statement": "Deploying more capital - steady lads",
        "source": "Tweet @stablekwon, May 9 2022",
        "category": "stablecoin",
        "date": "2022-05-09",
        "outcome_score": 0.0,
        "outcome_detail": (
            "Capital deployment failed catastrophically. UST never repegged. Within 48 hours "
            "LUNA went from ~$30 to under $1, eventually reaching $0.00001. LFG burned "
            "through ~$3.5 billion in Bitcoin reserves. This became one of crypto's most infamous memes."
        ),
        "evidence": "LFG reserve disclosures, on-chain BTC movements",
        "bias": 0.5,
        "source_type": "social_media",
        "source_url": "https://x.com/stablekwon/status/1523733542492016640",
    },

    # ─── ANCHOR PROTOCOL / YIELD ───
    {
        "statement": (
            "Anchor's 20% yield is sustainable. I am resolved to finding ways of "
            "subsidizing the yield reserve. Maintaining the most attractive yield in "
            "DeFi will strengthen growth and build up moats"
        ),
        "source": "Twitter statements and public AMAs, Jan-Feb 2022",
        "category": "defi_yield",
        "date": "2022-01-28",
        "outcome_score": 0.0,
        "outcome_detail": (
            "20% yield was unsustainable, as multiple developers warned. An Anchor dev "
            "claimed he warned Kwon before launch. $450M emergency injection in Feb 2022 "
            "bought 3 months before total collapse. 75% of all UST was in Anchor, making "
            "the yield the single point of failure for the entire ecosystem."
        ),
        "evidence": "Anchor reserve data, Cointelegraph developer interview",
        "bias": 0.5,
        "deadline": "2022-12-31",
        "source_type": "official",
        "source_url": "https://cointelegraph.com/news/anchor-dev-claims-he-warned-do-kwon-over-unsustainable-20-interest-rate",
    },

    # ─── LUNA FOUNDATION GUARD / BTC RESERVE ───
    {
        "statement": (
            "Luna Foundation Guard will accumulate $10 billion in Bitcoin reserves "
            "to backstop UST by Q3 2022. For the first time, you're starting to see "
            "a pegged currency attempting to observe the Bitcoin standard"
        ),
        "source": "Multiple interviews and announcements, March-May 2022",
        "category": "reserves",
        "date": "2022-03-01",
        "outcome_score": 0.1,
        "outcome_detail": (
            "LFG accumulated ~80,394 BTC (~$3.5B), reaching 35% of the $10B goal. "
            "All 80K BTC were dumped during the May crash trying to defend the peg and "
            "failed. Post-crash, LFG held only 313 BTC. Goal never reached. "
            "South Korean authorities alleged 3,313 BTC moved to KuCoin/OKX."
        ),
        "evidence": "LFG disclosures, on-chain analysis, CNBC reporting",
        "bias": 0.4,
        "deadline": "2022-09-30",
        "source_type": "official",
        "source_url": "https://www.cnbc.com/2022/05/05/luna-foundation-guard-bolsters-stablecoin-reserve-by-raising-1point5-billion-in-bitcoin.html",
    },

    # ─── PRICE BETS ───
    {
        "statement": (
            "LUNA will be above $88 one year from now. $1 million bet with @AlgodTrading, "
            "escrow held by Cobie"
        ),
        "source": "Twitter exchange @stablekwon and @AlgodTrading, March 9 2022",
        "category": "price_prediction",
        "date": "2022-03-09",
        "outcome_score": 0.0,
        "outcome_detail": (
            "LUNA crashed to $0 in May 2022, two months into the one-year bet. "
            "Algod won decisively. Cobie paid out shortly after LUNA went to zero. "
            "Do Kwon lost $1M."
        ),
        "evidence": "Cobie escrow wallet, on-chain settlement",
        "bias": 0.3,
        "deadline": "2023-03-14",
        "source_type": "social_media",
        "source_url": "https://cryptobriefing.com/terras-founder-is-betting-millions-on-luna-holding-its-highs/",
    },
    {
        "statement": (
            "LUNA will be above $88 one year from now. $10 million bet with "
            "@GiganticRebirth, escrow held by Cobie"
        ),
        "source": "Twitter exchange @stablekwon and @GiganticRebirth, March 14-15 2022",
        "category": "price_prediction",
        "date": "2022-03-14",
        "outcome_score": 0.0,
        "outcome_detail": (
            "LUNA crashed to $0 in May 2022. GCR won. Combined with Algod bet, "
            "Do Kwon lost $11M total. Cobie hedged escrow on FTX, which collapsed "
            "in Nov 2022, complicating the GCR payout."
        ),
        "evidence": "Escrow wallet transactions, CryptoBriefing reporting",
        "bias": 0.3,
        "deadline": "2023-03-14",
        "source_type": "social_media",
        "source_url": "https://beincrypto.com/luna-price-bet-stakes-hit-10m-as-terra-ceo-takes-second-wager/",
    },

    # ─── HUBRIS / MOCKING CRITICS ───
    {
        "statement": (
            "I don't debate the poor on Twitter, and sorry I don't have any change "
            "on me for her at the moment"
        ),
        "source": "Tweet @stablekwon responding to economist Frances Coppola, July 1 2021",
        "category": "credibility",
        "date": "2021-07-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "Frances Coppola's criticism of the algorithmic stablecoin model was "
            "vindicated by UST's total collapse. Kwon later admitted his Twitter "
            "persona was 'cringe' created for 'entertainment value.'"
        ),
        "evidence": "Coinage interview admission, UST collapse",
        "bias": 0.5,
        "source_type": "social_media",
        "source_url": "https://x.com/stablekwon/status/1410491186196795398",
    },
    {
        "statement": (
            "95% of crypto projects are going to die, but there's also entertainment "
            "in watching companies die too"
        ),
        "source": "Video interview with chess streamer Alexandra Botez, ~May 3 2022",
        "category": "credibility",
        "date": "2022-05-03",
        "outcome_score": 0.0,
        "outcome_detail": (
            "Eight days after this interview was published, Terra/LUNA itself 'died,' "
            "losing 99.99% of its value. The quote became one of crypto's most ironic "
            "statements ever made."
        ),
        "evidence": "LUNA price data May 2022, video interview",
        "bias": 0.3,
        "source_type": "interview",
        "source_url": "https://cryptopotato.com/terras-do-kwon-8-days-ago-theres-entertainment-in-watching-companies-die/",
    },
    {
        "statement": "Baby Luna. My dearest creation named after my greatest invention",
        "source": "Tweet @stablekwon, April 16 2022",
        "category": "personal",
        "date": "2022-04-16",
        "outcome_score": 0.0,
        "outcome_detail": (
            "Less than one month later, his 'greatest invention' LUNA crashed from ~$80 "
            "to fractions of a penny, wiping out ~$40 billion. His wife requested police "
            "protection due to an angry investor showing up at their home."
        ),
        "evidence": "LUNA price history, news reports of wife's police request",
        "bias": 0.3,
        "source_type": "social_media",
        "source_url": "https://x.com/stablekwon/status/1515501798442008577",
    },

    # ─── POST-CRASH CLAIMS ───
    {
        "statement": (
            "I am heartbroken about the pain my invention has brought on all of you. "
            "Neither I nor any institutions that I am affiliated with profited in any way "
            "from this incident. I sold no luna nor ust during the crisis"
        ),
        "source": "Tweet @stablekwon and Terra governance forum, May 13 2022",
        "category": "transparency",
        "date": "2022-05-13",
        "outcome_score": 0.0,
        "outcome_detail": (
            "His claim of not profiting was contradicted by SEC/DOJ findings. "
            "Found liable for civil fraud (April 2024). Pleaded guilty to wire fraud "
            "and conspiracy (August 2025). Sentenced to 15 years in prison."
        ),
        "evidence": "SEC civil verdict April 2024, DOJ guilty plea August 2025",
        "bias": 0.6,
        "source_type": "official",
        "source_url": "https://www.coindesk.com/business/2022/05/13/do-kwon-i-am-heartbroken-over-pain-caused-by-ust-collapse",
    },
    {
        "statement": (
            "Terra is more than UST. The community must reconstitute the chain. "
            "This is a chance to rise up anew from the ashes"
        ),
        "source": "Terra governance forum post, May 16 2022",
        "category": "recovery",
        "date": "2022-05-16",
        "outcome_score": 0.05,
        "outcome_detail": (
            "Terra 2.0 launched May 28, 2022. LUNA 2.0 dropped ~80% on day one. "
            "Old chain renamed Terra Classic (LUNC). Both tokens trade at fractions "
            "of peak values. The 'revival' failed to restore any meaningful value."
        ),
        "evidence": "LUNA 2.0 price data, Terra Classic market cap",
        "bias": 0.5,
        "source_type": "official",
        "source_url": "https://www.coindesk.com/business/2022/05/16/kwon-proposes-forking-terra-in-revival-plan-2/",
    },
    {
        "statement": "Terra and LUNA were essentially my life. I bet big and I lost. I alone am responsible",
        "source": "Coinage Media interview (first post-crash interview), August 2022",
        "category": "transparency",
        "date": "2022-08-01",
        "outcome_score": 0.1,
        "outcome_detail": (
            "The 'I bet big and I lost' framing implied good faith. SEC later proved "
            "Kwon secretly arranged market manipulation with Jump Trading, misrepresented "
            "Chai payment volume, and deceived investors. Convicted of fraud, not just "
            "a bad bet."
        ),
        "evidence": "SEC trial evidence, DOJ charges",
        "bias": 0.6,
        "source_type": "interview",
        "source_url": "https://www.coinage.media/s1/inside-cryptos-largest-collapse-with-terras-do-kwon",
    },

    # ─── FLEEING / COOPERATION LIES ───
    {
        "statement": "I am not 'on the run' or anything similar. We are in full cooperation and don't have anything to hide",
        "source": "Tweet @stablekwon, September 17 2022",
        "category": "legal",
        "date": "2022-09-17",
        "outcome_score": 0.0,
        "outcome_detail": (
            "Arrested March 23, 2023 at Podgorica Airport in Montenegro while trying to "
            "board a flight to Dubai using a forged Costa Rican passport. Seoul prosecutors "
            "confirmed he told them through his lawyer he had 'no intention to appear for "
            "questioning.' Extradited to US December 2024."
        ),
        "evidence": "Montenegro arrest records, Interpol Red Notice, Seoul prosecutor statements",
        "bias": 0.7,  # Actively fleeing while claiming cooperation
        "source_type": "social_media",
        "source_url": "https://cointelegraph.com/news/terra-co-founder-do-kwon-says-he-s-not-on-the-run",
    },
    {
        "statement": (
            "How Red Notices work is something that I don't really understand very well. "
            "We'll do everything that we can to make clarifications"
        ),
        "source": "Unchained Podcast interview with Laura Shin, October 2022",
        "category": "legal",
        "date": "2022-10-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "Kwon understood Red Notices well enough to flee across multiple countries "
            "with forged identity documents. Arrested in Montenegro with a fake Costa "
            "Rican passport. The feigned ignorance was another deception."
        ),
        "evidence": "Montenegro arrest report, forged passport evidence",
        "bias": 0.7,
        "source_type": "interview",
    },

    # ─── HIDDEN PREDECESSOR ───
    {
        "statement": (
            "UST's algorithmic mechanism is novel and robust, designed from first principles "
            "to maintain the dollar peg through market incentives"
        ),
        "source": "Multiple Terra whitepapers and presentations, 2020-2022",
        "category": "stablecoin",
        "date": "2020-09-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "Kwon never disclosed his involvement in Basis Cash, a prior failed algorithmic "
            "stablecoin on Ethereum using the same mechanism. Basis Cash launched late 2020 "
            "under pseudonyms 'Rick' and 'Morty,' never achieved its peg, fell below $0.01. "
            "Kwon launched UST using the same fundamental mechanism that already failed."
        ),
        "evidence": "CoinDesk investigation, former Terraform engineer Hyungsuk Kang testimony",
        "bias": 0.6,
        "source_type": "official",
        "source_url": "https://www.coindesk.com/tech/2022/05/11/usts-do-kwon-was-behind-earlier-failed-stablecoin-ex-terra-colleagues-say",
    },
]

# ──────────────────────────────────────────────────────────────────────

print("=" * 70)
print("SAY/DO POC: Do Kwon Credibility Index")
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
    print(f"    {cat:20s}  {total} statements, {rate:.0%} follow-through")

# Phase 4: Top Contradictions
print("\nPHASE 4: Top Contradictions")
print("=" * 70)
contradictions = engine.get_entity_contradictions(ENTITY, min_score=0.0)
for i, c in enumerate(contradictions[:10], 1):
    print(f"  {i}. [score={c['score']:.3f}] {c['summary'][:100]}")

# Phase 5: Predictions
print("\nPHASE 5: Follow-Through Predictions (new claims)")
print("=" * 70)
from omega.saydo.prediction import predict_followthrough

test_statements = [
    ("I will cooperate fully with US authorities", "legal"),
    ("Terra 3.0 will restore value to original holders", "recovery"),
    ("The algorithm was sound, implementation was the issue", "stablecoin"),
    ("I never intended to defraud anyone", "transparency"),
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
if ftr < 0.15:
    print(f"  PASS: Follow-through rate {ftr:.0%} < 15%")
else:
    print(f"  WARN: Follow-through rate {ftr:.0%} >= 15%")

print(f"\n  Contradiction score: {profile['contradiction_score']:.3f}")
print(f"  Total broken: {profile['outcomes_broken']}/{profile['total_statements']}")

print("\n" + "=" * 70)
print("POC COMPLETE")
print("=" * 70)
