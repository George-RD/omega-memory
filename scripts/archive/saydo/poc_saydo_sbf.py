#!/usr/bin/env python3
"""Say/Do POC: Sam Bankman-Fried (SBF) Credibility Index.

Populates the Say/Do engine with SBF's well-documented public statements
and their known outcomes, then generates the full credibility profile.

Validation target: SBF should score BELOW 0.10 credibility.
One of the most documented fraud cases in financial history.

All statements sourced from public record (tweets, interviews, congressional
testimony, trial transcripts, court filings).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omega.sqlite_store import SQLiteStore
from omega.saydo.engine import get_saydo_engine, _engine_instance
import omega.saydo.engine as eng_mod
import omega.bridge as bridge

DB_PATH = Path(__file__).parent.parent / "data" / "poc_saydo_sbf.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

if DB_PATH.exists():
    DB_PATH.unlink()

store = SQLiteStore(db_path=str(DB_PATH))
bridge._store_instance = store
eng_mod._engine_instance = None

engine = get_saydo_engine()

ENTITY = "Sam Bankman-Fried"
ENTITY_TYPE = "person"

DATA = [
    # ─── CUSTOMER FUND SAFETY CLAIMS ───
    {
        "statement": (
            "FTX has enough to cover all client holdings. We don't invest client assets "
            "(even in treasuries). We have been processing all withdrawals, and will "
            "continue to be"
        ),
        "source": "Tweet @SBF_FTX, November 7, 2022",
        "category": "customer_funds",
        "date": "2022-11-07",
        "outcome_score": 0.0,
        "outcome_detail": (
            "FTX did not have enough to cover client holdings. An $8 billion hole was "
            "discovered. Customer funds had been systematically transferred to Alameda "
            "Research. FTX halted withdrawals within 24 hours of this tweet and filed "
            "bankruptcy 4 days later."
        ),
        "evidence": "FTX bankruptcy filing Nov 11 2022, John Ray III testimony, trial evidence",
        "bias": 0.7,
        "source_type": "social_media",
        "source_url": "https://twitter.com/SBF_FTX/status/1589598285857931264",
    },
    {
        "statement": (
            "A competitor is trying to go after us with false rumors. FTX is fine. "
            "Assets are fine"
        ),
        "source": "Tweet @SBF_FTX, November 7, 2022",
        "category": "customer_funds",
        "date": "2022-11-07",
        "outcome_score": 0.0,
        "outcome_detail": (
            "FTX was not fine. Assets were not fine. The 'false rumors' from CoinDesk's "
            "reporting about Alameda's balance sheet were accurate. FTX collapsed within "
            "4 days. Described by new CEO John Ray III as 'a complete failure of corporate "
            "controls and such a complete absence of trustworthy financial information.'"
        ),
        "evidence": "CoinDesk Alameda balance sheet report, FTX bankruptcy, Ray III declaration",
        "bias": 0.7,
        "source_type": "social_media",
    },
    {
        "statement": (
            "FTX does not invest client assets, even in treasuries. Customer deposits "
            "are backed 1:1"
        ),
        "source": "Multiple public statements and interviews throughout 2021-2022",
        "category": "customer_funds",
        "date": "2021-06-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "FTX systematically transferred billions in customer funds to Alameda Research "
            "through a secret backdoor in FTX's code. Alameda used customer deposits for "
            "trading, venture investments, real estate, political donations, and personal "
            "expenses. The jury found SBF guilty on all counts."
        ),
        "evidence": "Trial testimony, code analysis of FTX backdoor, jury verdict Oct 2023",
        "bias": 0.7,
        "source_type": "official",
    },

    # ─── ALAMEDA/FTX SEPARATION CLAIMS ───
    {
        "statement": (
            "Alameda is a totally separate entity from FTX. There is no special treatment. "
            "Alameda is just one of many market makers on FTX"
        ),
        "source": "Multiple interviews, congressional testimony 2021-2022",
        "category": "corporate_governance",
        "date": "2021-01-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "Alameda had a secret $65 billion line of credit from FTX that no other "
            "market maker had. A hidden 'allow_negative' flag in FTX's code exempted "
            "Alameda from liquidation. Alameda's losses were covered by customer funds. "
            "The two entities were deeply intertwined with shared offices and staff."
        ),
        "evidence": "Trial testimony from Gary Wang and Caroline Ellison, code evidence",
        "bias": 0.7,
        "source_type": "official",
    },
    {
        "statement": (
            "Alameda's trading on FTX follows the same rules as every other market maker. "
            "They get liquidated just like anyone else"
        ),
        "source": "Odd Lots podcast and other media appearances, 2022",
        "category": "corporate_governance",
        "date": "2022-04-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "Gary Wang testified he created a special exemption in FTX's code at SBF's "
            "direction that prevented Alameda from being liquidated. Alameda had a secret "
            "'allow_negative' balance feature allowing it to withdraw more than its deposits, "
            "effectively borrowing customer funds without limit."
        ),
        "evidence": "Gary Wang trial testimony, FTX code analysis",
        "bias": 0.7,
        "source_type": "interview",
    },

    # ─── REGULATORY/COMPLIANCE CLAIMS ───
    {
        "statement": (
            "We believe in regulation. FTX is one of the most regulated exchanges in the "
            "world. We work proactively with regulators in every jurisdiction"
        ),
        "source": "Congressional testimony and multiple public appearances, 2021-2022",
        "category": "regulatory",
        "date": "2022-02-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "FTX had virtually no internal controls, no board of directors, and used "
            "QuickBooks for a $32 billion exchange. Regulatory engagement was primarily "
            "a PR strategy. SBF privately called regulators 'dumb' and compliance efforts "
            "'just PR.' John Ray III said he had never seen 'such a complete failure of "
            "corporate controls.'"
        ),
        "evidence": "Ray III bankruptcy declaration, SBF private messages revealed at trial",
        "bias": 0.6,
        "source_type": "testimony",
    },
    {
        "statement": (
            "I testified before Congress about the need for sensible crypto regulation "
            "because I believe in protecting consumers and building trust in the industry"
        ),
        "source": "Congressional testimony, December 2021 and February 2022",
        "category": "regulatory",
        "date": "2021-12-08",
        "outcome_score": 0.0,
        "outcome_detail": (
            "Congressional testimony was revealed to be a strategy to gain regulatory "
            "favor while operating a massive fraud. SBF's private communications showed "
            "he viewed regulation as a competitive moat against rivals, not consumer "
            "protection. He said in DMs that his public ethics talk was 'just what "
            "reputations are made of.'"
        ),
        "evidence": "Trial exhibits of private messages, Vox interview Nov 2022",
        "bias": 0.6,
        "source_type": "testimony",
    },

    # ─── EFFECTIVE ALTRUISM CLAIMS ───
    {
        "statement": (
            "I got into crypto to earn money to give it away. I'm an effective altruist. "
            "The goal is to earn as much as possible to donate to the most effective causes"
        ),
        "source": "Multiple interviews, 80,000 Hours podcast, public statements 2019-2022",
        "category": "philanthropy",
        "date": "2019-01-01",
        "outcome_score": 0.05,
        "outcome_detail": (
            "SBF's actual charitable giving was a fraction of his pledges. Much of the "
            "'donations' were to politically connected organizations or for personal influence. "
            "The EA framing was weaponized for reputation laundering. In the Vox interview "
            "post-collapse, SBF said the ethics talk was 'just what reputations are made of' "
            "and 'this dumb game we woke westerners play.'"
        ),
        "evidence": "Vox interview Nov 2022, FTX Foundation dissolution, trial testimony",
        "bias": 0.6,
        "source_type": "interview",
    },
    {
        "statement": (
            "I plan to give away $1 billion or more to pandemic prevention over my lifetime. "
            "Guarding Against Pandemics is one of my top priorities"
        ),
        "source": "Public pledges and Guarding Against Pandemics organization, 2021-2022",
        "category": "philanthropy",
        "date": "2021-06-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "Guarding Against Pandemics was primarily a political lobbying operation run "
            "by SBF's brother Gabe Bankman-Fried. Actual pandemic prevention funding was "
            "minimal. The organization shut down after FTX's collapse. The $1B pledge was "
            "never remotely close to being fulfilled. Gabe faced his own legal troubles."
        ),
        "evidence": "GAP dissolution, Gabe Bankman-Fried investigation",
        "bias": 0.5,
        "deadline": "2030-12-31",
        "source_type": "official",
    },

    # ─── PERSONAL FRUGALITY / CHARACTER CLAIMS ───
    {
        "statement": (
            "I sleep on a bean bag in the office. I drive a Toyota Corolla. I don't care "
            "about money or material possessions. I want to give it all away"
        ),
        "source": "Multiple profiles: NYT, Forbes, Bloomberg, 2021-2022",
        "category": "personal_character",
        "date": "2021-09-01",
        "outcome_score": 0.05,
        "outcome_detail": (
            "SBF and FTX insiders spent lavishly: $256M on Bahamas real estate including "
            "a $30M penthouse for SBF's parents, $16.4M in private jet expenses, luxury "
            "cars, $150M in personal loans to executives. The frugality persona was a "
            "calculated PR strategy. He privately admitted the 'bean bag' image was strategic."
        ),
        "evidence": "FTX bankruptcy filings, property records, trial testimony",
        "bias": 0.6,
        "source_type": "interview",
    },
    {
        "statement": (
            "I'm vegan. I don't care about luxury. The utilitarian calculus is all that "
            "matters to me"
        ),
        "source": "Multiple media profiles, 2021-2022",
        "category": "personal_character",
        "date": "2021-06-01",
        "outcome_score": 0.1,
        "outcome_detail": (
            "While SBF maintained some personal simplicity, the utilitarian framing was "
            "used to justify massive fraud. Caroline Ellison testified that SBF told her "
            "'the rules don't apply to people like us' because their expected value "
            "calculations justified breaking laws. The philosophy was weaponized."
        ),
        "evidence": "Caroline Ellison trial testimony, Vox interview",
        "bias": 0.5,
        "source_type": "interview",
    },

    # ─── POLITICAL DONATIONS ───
    {
        "statement": (
            "I donated to both parties transparently. My political giving is about policy, "
            "not influence. I gave about the same to both sides"
        ),
        "source": "Multiple interviews, 2022",
        "category": "political",
        "date": "2022-01-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "SBF was the second-largest individual donor to Democrats in the 2022 midterms "
            "($40M+). His Republican donations were largely made through dark money channels "
            "and straw donors to hide the partisan split. He was charged with illegal campaign "
            "finance violations and using straw donors. The 'both sides' claim was false."
        ),
        "evidence": "FEC records, DOJ indictment campaign finance counts, Ryan Salame testimony",
        "bias": 0.6,
        "source_type": "interview",
    },

    # ─── POST-COLLAPSE CLAIMS ───
    {
        "statement": (
            "I didn't knowingly commingle funds. I made mistakes but I didn't commit fraud. "
            "I didn't ever try to commit fraud on anyone"
        ),
        "source": "Multiple post-collapse interviews and tweets, November-December 2022",
        "category": "legal",
        "date": "2022-11-14",
        "outcome_score": 0.0,
        "outcome_detail": (
            "Found guilty on all 7 counts including wire fraud, conspiracy to commit wire "
            "fraud, securities fraud, commodities fraud, and money laundering. The jury "
            "deliberated for under 5 hours. Sentenced to 25 years in prison on March 28, "
            "2024. Judge Lewis Kaplan said SBF committed perjury on the stand."
        ),
        "evidence": "Jury verdict Nov 2, 2023; sentencing March 28, 2024",
        "bias": 0.7,
        "source_type": "interview",
    },
    {
        "statement": (
            "I'm going to make everyone whole. I want to make customers whole. "
            "I'm going to figure out a way to do that"
        ),
        "source": "Twitter Spaces and DMs with reporters, November 2022",
        "category": "customer_funds",
        "date": "2022-11-15",
        "outcome_score": 0.1,
        "outcome_detail": (
            "SBF did not make anyone whole. The FTX bankruptcy estate under John Ray III "
            "eventually recovered enough assets to repay customers, but this was entirely "
            "due to the bankruptcy team's work and crypto market recovery, not any action "
            "by SBF. SBF was in prison. He actively tried to interfere with the bankruptcy "
            "process."
        ),
        "evidence": "FTX bankruptcy proceedings, customer repayment plan 2024",
        "bias": 0.7,
        "source_type": "social_media",
    },
    {
        "statement": (
            "I had a bad month. Look, I've had a bad month. But I don't think that means "
            "I committed fraud. I think what happened is we got hit by a massive "
            "market crash"
        ),
        "source": "DealBook Summit interview with Andrew Ross Sorkin, November 30, 2022",
        "category": "legal",
        "date": "2022-11-30",
        "outcome_score": 0.0,
        "outcome_detail": (
            "The framing of 'a bad month' and 'market crash' was rejected by the jury. "
            "Evidence showed years of systematic fraud, not a sudden market event. The "
            "$8B hole existed long before November 2022. Customer funds were misappropriated "
            "starting as early as 2019. Convicted on all counts."
        ),
        "evidence": "Trial testimony showing years of fund misuse, jury verdict",
        "bias": 0.7,
        "source_type": "interview",
        "source_url": "https://www.youtube.com/watch?v=UEJTFVxC-9s",
    },

    # ─── RISK MANAGEMENT ───
    {
        "statement": (
            "We have a very robust risk engine. FTX's risk management system automatically "
            "liquidates positions. We take risk management very seriously"
        ),
        "source": "Multiple interviews and FTX marketing materials, 2021-2022",
        "category": "corporate_governance",
        "date": "2021-01-01",
        "outcome_score": 0.0,
        "outcome_detail": (
            "FTX had no real risk management for its largest counterparty. Alameda was "
            "exempted from the risk engine entirely. There was no chief risk officer. "
            "The company used QuickBooks and Slack for financial tracking. Nishad Singh "
            "testified about the complete absence of financial controls."
        ),
        "evidence": "Trial testimony, Ray III bankruptcy declaration",
        "bias": 0.6,
        "source_type": "official",
    },

    # ─── ACQUISITION PROMISES ───
    {
        "statement": (
            "FTX will bail out struggling crypto companies. We have a responsibility "
            "to step in and protect the ecosystem. We have the balance sheet to do it"
        ),
        "source": "Multiple interviews during crypto crash, June-July 2022",
        "category": "business",
        "date": "2022-06-22",
        "outcome_score": 0.05,
        "outcome_detail": (
            "FTX did provide credit facilities to BlockFi (~$400M) and Voyager (~$200M). "
            "But these 'bailouts' were structured as acquisitions using customer money FTX "
            "didn't actually have. When FTX collapsed, both BlockFi and Voyager went bankrupt "
            "again. The 'balance sheet' SBF cited was largely customer deposits."
        ),
        "evidence": "BlockFi bankruptcy, Voyager bankruptcy, trial testimony",
        "bias": 0.6,
        "source_type": "interview",
    },

    # ─── THE VOX INTERVIEW ADMISSION ───
    {
        "statement": (
            "Yeah, I mean that's what reputations are made of, to some extent. "
            "I feel bad for those who get f***ed by it. By this dumb game we "
            "woke westerners play where we say all the right shibboleths and "
            "so everyone likes us"
        ),
        "source": "DM conversation with Vox reporter Kelsey Piper, November 15, 2022",
        "category": "personal_character",
        "date": "2022-11-15",
        "outcome_score": 0.0,
        "outcome_detail": (
            "This candid admission revealed that SBF's entire public persona, his "
            "EA commitments, regulatory advocacy, and ethics talk, was calculated "
            "reputation management. He admitted the 'ethics stuff' was largely performative. "
            "This became key evidence of his knowing deception."
        ),
        "evidence": "Published Vox DM transcript",
        "bias": 0.3,  # Low bias because he was being honest for once
        "source_type": "social_media",
        "source_url": "https://www.vox.com/future-perfect/2022/11/15/23460323/sam-bankman-fried-ftx-cryptocurrency-effective-altruism-crypto-bahamas-philanthropy",
    },
]

# ──────────────────────────────────────────────────────────────────────

print("=" * 70)
print("SAY/DO POC: Sam Bankman-Fried (SBF) Credibility Index")
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
    ("I will appeal my conviction and be exonerated", "legal"),
    ("I never intended to defraud anyone", "personal_character"),
    ("The customers will be made whole", "customer_funds"),
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
    if cred < 0.10:
        print(f"  PASS: Credibility score {cred:.3f} < 0.10 threshold")
    else:
        print(f"  FAIL: Credibility score {cred:.3f} >= 0.10 threshold")
        print(f"  The credibility system may need tuning.")
else:
    print("  WARN: No credibility score computed")

ftr = profile.get("follow_through_rate", 1.0)
if ftr < 0.10:
    print(f"  PASS: Follow-through rate {ftr:.0%} < 10%")
else:
    print(f"  WARN: Follow-through rate {ftr:.0%} >= 10%")

print(f"\n  Contradiction score: {profile['contradiction_score']:.3f}")
print(f"  Total broken: {profile['outcomes_broken']}/{profile['total_statements']}")

print("\n" + "=" * 70)
print("POC COMPLETE")
print("=" * 70)
