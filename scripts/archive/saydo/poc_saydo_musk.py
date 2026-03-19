#!/usr/bin/env python3
"""Say/Do POC: Elon Musk Contradiction Index.

Populates the Say/Do engine with well-documented public statements and
their known outcomes. Focuses on verifiable claims with clear timelines.

All statements sourced from public record: earnings calls, tweets,
conference presentations, interviews, regulatory filings.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omega.sqlite_store import SQLiteStore
from omega.saydo.engine import get_saydo_engine, _normalize_entity
import omega.saydo.engine as eng_mod
import omega.bridge as bridge

DB_PATH = Path(__file__).parent.parent / "data" / "poc_saydo_musk.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

store = SQLiteStore(db_path=str(DB_PATH))
bridge._store_instance = store
eng_mod._engine_instance = None

engine = get_saydo_engine()

ENTITY = "Elon Musk"
ENTITY_TYPE = "CEO"

# ──────────────────────────────────────────────────────────────────────
# (statement, source, category, date, followed_through, outcome_detail, evidence)
# ──────────────────────────────────────────────────────────────────────

DATA = [
    # ═══════════════════════════════════════════════════════════════════
    # TESLA - SELF-DRIVING / AUTONOMY
    # ═══════════════════════════════════════════════════════════════════
    (
        "A Tesla will drive itself coast to coast from LA to New York by the end of 2017",
        "Tesla Autonomy Day presentation, October 2016",
        "autonomy",
        "2016-10-19",
        False,
        "Coast-to-coast autonomous drive never completed. As of 2026, Tesla FSD still requires driver supervision and is SAE Level 2. The demo was never performed.",
        "Tesla press releases, NHTSA classifications",
    ),
    (
        "By mid-2020 Tesla's Full Self-Driving capability will be so good that you won't need to pay attention to the road",
        "Tesla Q4 2019 earnings call, January 2020",
        "autonomy",
        "2020-01-29",
        False,
        "FSD Beta remained Level 2 requiring constant driver attention. NHTSA opened multiple investigations. Tesla's own terms of service require hands on wheel at all times.",
        "NHTSA investigations, Tesla FSD terms of service",
    ),
    (
        "There will be over a million Tesla robotaxis on the road by the end of 2020",
        "Tesla Autonomy Day, April 2019",
        "autonomy",
        "2019-04-22",
        False,
        "Zero robotaxis deployed by end of 2020. As of early 2026, Tesla has not launched a commercial robotaxi service. Waymo and Cruise operated robotaxis years before Tesla.",
        "Tesla filings, industry reports",
    ),
    (
        "FSD will be feature-complete by end of 2020",
        "Multiple earnings calls and tweets, 2020",
        "autonomy",
        "2020-07-22",
        False,
        "FSD Beta v12 (2024) still not feature-complete. Unprotected left turns, construction zones, adverse weather remain problematic. Multiple NHTSA recalls issued for FSD.",
        "NHTSA recall records, Tesla release notes",
    ),
    (
        "Buying a Tesla today is an investment because it will appreciate in value as a robotaxi asset",
        "Tesla Autonomy Day, April 2019",
        "autonomy",
        "2019-04-22",
        False,
        "Teslas depreciated like normal cars. No robotaxi network launched. Used Tesla prices followed standard depreciation curves. No owner earned robotaxi income.",
        "Used car market data, KBB/Edmunds valuations",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # TESLA - PRODUCTS / TIMELINES
    # ═══════════════════════════════════════════════════════════════════
    (
        "Tesla Semi will begin production and deliveries in 2019",
        "Tesla Semi unveil, November 2017",
        "product_delivery",
        "2017-11-16",
        False,
        "Semi deliveries didn't begin until December 2022, three years late. Only delivered to PepsiCo initially. Volume production still extremely limited through 2025.",
        "Tesla delivery reports, SEC filings",
    ),
    (
        "The new Tesla Roadster will begin production in 2020 with a 250+ mph top speed",
        "Tesla Roadster unveil, November 2017",
        "product_delivery",
        "2017-11-16",
        False,
        "Roadster repeatedly delayed. Not in production as of early 2026. Originally promised 2020, then 2022, then 2023, then 'maybe 2025.' SpaceX thruster package also promised but not delivered.",
        "Tesla announcements, earnings call transcripts",
    ),
    (
        "Cybertruck will start at $39,900 and begin production in late 2021",
        "Cybertruck unveil, November 2019",
        "product_delivery",
        "2019-11-21",
        False,
        "Cybertruck production started late 2023, two years late. Starting price was $60,990 (Rear-Wheel Drive), 53% above promised price. Design changed significantly from reveal.",
        "Tesla configurator, delivery records",
    ),
    (
        "Tesla will produce 500,000 cars per year by 2018",
        "Tesla Q2 2016 earnings call",
        "production",
        "2016-08-03",
        False,
        "Tesla produced ~245,000 vehicles in 2018. Did not hit 500K annual production until 2020. Model 3 'production hell' caused major delays in 2017-2018.",
        "Tesla quarterly production reports",
    ),
    (
        "Tesla will produce 20 million vehicles per year by 2030",
        "Tesla investor presentation, 2020",
        "production",
        "2020-09-22",
        False,
        "Tesla produced ~1.8M vehicles in 2023, then declined to ~1.79M in 2024. Would need 11x growth in 5 years. No credible path to 20M by 2030. Demand softening visible by 2024.",
        "Tesla annual delivery reports",
    ),
    (
        "Tesla Model Y will be the best-selling car of any kind globally",
        "Multiple statements, 2022-2023",
        "production",
        "2022-01-26",
        True,
        "Model Y became the world's best-selling car in 2023 with ~1.2M units, first EV to achieve this. Outsold Toyota Corolla and RAV4.",
        "JATO Dynamics, global sales data",
    ),
    (
        "Tesla will build a $25,000 affordable electric car",
        "Tesla Battery Day, September 2020",
        "product_delivery",
        "2020-09-22",
        False,
        "Affordable Tesla reportedly cancelled in April 2024 per Reuters. Musk denied it but no $25K car has been produced or announced with a firm timeline. Focus shifted to robotaxi platform.",
        "Reuters reporting, Tesla earnings calls",
    ),
    (
        "Tesla will achieve a gross margin of 30%+ long term",
        "Multiple earnings calls, 2021-2022",
        "financial",
        "2022-01-26",
        False,
        "Gross margins peaked around 29% in Q1 2022, then declined to ~17-18% by 2024 due to aggressive price cuts. Margins compressed significantly to defend market share.",
        "Tesla quarterly earnings reports",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # SPACEX
    # ═══════════════════════════════════════════════════════════════════
    (
        "Falcon Heavy will launch in 2013",
        "SpaceX announcements, 2011-2012",
        "spacex",
        "2012-04-05",
        False,
        "Falcon Heavy first launch occurred February 6, 2018, five years behind original schedule. However, it did successfully launch and land all three boosters on subsequent flights.",
        "SpaceX launch records",
    ),
    (
        "SpaceX will send two tourists around the Moon by end of 2018",
        "SpaceX announcement, February 2017",
        "spacex",
        "2017-02-27",
        False,
        "Mission never happened by 2018. Concept evolved into dearMoon project with Yusaku Maezawa, which was ultimately cancelled in 2024 due to Starship development delays.",
        "SpaceX announcements, dearMoon project",
    ),
    (
        "SpaceX will land humans on Mars by 2024",
        "IAC presentation, September 2016; reiterated 2017",
        "spacex",
        "2016-09-27",
        False,
        "No human Mars mission attempted or scheduled by 2024. Starship still in testing phase. Most optimistic estimates now target late 2020s for uncrewed Mars landing.",
        "SpaceX presentations, NASA Artemis schedule",
    ),
    (
        "Starship will reach orbit in 2020",
        "Multiple statements and tweets, 2019",
        "spacex",
        "2019-09-28",
        False,
        "First Starship orbital attempt was April 2023, three years late. First successful orbit and controlled ocean landing achieved in 2024 (IFT-4). Vehicle evolved significantly.",
        "SpaceX launch records, FAA licenses",
    ),
    (
        "SpaceX will make humanity a multiplanetary species",
        "Multiple presentations, ongoing",
        "spacex",
        "2016-09-27",
        False,
        "As of 2026, no human has traveled beyond low Earth orbit since Apollo 17 (1972). Starship development progressing but Mars colonization remains decades away at minimum.",
        "SpaceX progress reports",
    ),
    (
        "Falcon 9 will reduce launch costs by 100x through reusability",
        "Multiple presentations, 2010s",
        "spacex",
        "2014-03-01",
        False,
        "Falcon 9 significantly reduced launch costs (roughly 5-10x vs. competitors), but not 100x. Launches cost ~$67M vs. theoretical $2M if 100x reduction achieved. Still a major industry disruption.",
        "SpaceX pricing, industry analysis",
    ),
    (
        "SpaceX will successfully land and reuse orbital rocket boosters",
        "Multiple presentations, 2011-2015",
        "spacex",
        "2013-09-29",
        True,
        "First successful Falcon 9 landing December 21, 2015. First reflight March 30, 2017. By 2024, some boosters had flown 20+ times. Revolutionary achievement in spaceflight.",
        "SpaceX launch records",
    ),
    (
        "Starlink will provide global broadband internet coverage",
        "FCC filings and presentations, 2015-2018",
        "spacex",
        "2018-02-22",
        True,
        "Starlink operational in 70+ countries by 2024 with 2.3M+ subscribers. Achieved near-global coverage excluding polar regions. Revenue estimated at $6.6B in 2024.",
        "Starlink coverage maps, FCC filings, industry reports",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # TWITTER / X
    # ═══════════════════════════════════════════════════════════════════
    (
        "I am a free speech absolutist and Twitter will be a platform for free speech",
        "Multiple tweets and interviews, April 2022",
        "twitter",
        "2022-04-14",
        False,
        "Suspended journalists (NYT, CNN, WaPo) for reporting on @ElonJet. Banned accounts critical of him. Throttled links to competitors (Threads, Substack, Mastodon). Complied with government censorship demands in Turkey, India.",
        "Media reports, platform policy changes",
    ),
    (
        "I am buying Twitter to help humanity, not to make money",
        "Ted Talk and tweets, April 2022",
        "twitter",
        "2022-04-14",
        False,
        "Immediately monetized verification (Twitter Blue), cut moderation teams, pushed aggressive ad revenue schemes. Valued the company at $20B in internal fundraising (vs. $44B purchase), losing ~55% of value.",
        "SEC filings, Fidelity valuation markdowns",
    ),
    (
        "Twitter will become X, the everything app, like WeChat",
        "Multiple statements, 2022-2023",
        "twitter",
        "2022-10-04",
        False,
        "X rebranding launched July 2023. Payments feature announced but extremely limited (no broad financial services). Not an everything app. User engagement and ad revenue declined significantly vs. Twitter's peak.",
        "Platform analytics, advertiser reports",
    ),
    (
        "Twitter can operate effectively after reducing 80% of staff",
        "Statements during acquisition, October 2022",
        "twitter",
        "2022-10-28",
        False,
        "Widespread service degradation after mass layoffs. Trust & safety gutted. Increased spam, bot activity, and scam accounts. Advertisers fled (Musk acknowledged 50% ad revenue decline). Infrastructure incidents increased.",
        "Advertiser reports, platform outage records",
    ),
    (
        "We are going to crack down on bots on Twitter",
        "Pre-acquisition statements, 2022",
        "twitter",
        "2022-05-13",
        False,
        "Bot activity increased after acquisition by most measures. Spam replies proliferated. The original bot concern was used as attempted leverage to exit the deal, which a court rejected.",
        "Bot analysis reports, Delaware Chancery Court filings",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # THE BORING COMPANY
    # ═══════════════════════════════════════════════════════════════════
    (
        "The Boring Company will reduce tunneling costs to $10 million per mile, 10x cheaper than current costs",
        "TBC presentations, 2017-2018",
        "boring_company",
        "2017-12-17",
        False,
        "Las Vegas Convention Center Loop cost ~$47M for 0.8 miles (~$59M/mile). No evidence of achieving $10M/mile target. Still uses modified Tesla vehicles, not the high-speed pods originally promised.",
        "LVCVA contract, public records",
    ),
    (
        "Hyperloop will transport passengers from LA to San Francisco in 30 minutes",
        "Hyperloop white paper and presentations, 2013",
        "boring_company",
        "2013-08-12",
        False,
        "No Hyperloop built. Concept was open-sourced. Virgin Hyperloop tested a pod with passengers (2020) at only 107 mph before pivoting to cargo and eventually shutting down. Musk's own company focused on low-speed tunnels instead.",
        "Virgin Hyperloop records, TBC projects",
    ),
    (
        "The Las Vegas Loop will expand to cover the entire Las Vegas Strip and airport",
        "TBC and LVCVA presentations, 2021",
        "boring_company",
        "2021-06-10",
        False,
        "Convention Center Loop operates at low speed (~35 mph) with human drivers. Strip expansion repeatedly delayed. As of 2026, only the initial Convention Center Loop is operational. Far from the city-wide system proposed.",
        "LVCVA reports, Clark County permits",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # NEURALINK
    # ═══════════════════════════════════════════════════════════════════
    (
        "Neuralink will begin human clinical trials by end of 2020",
        "Neuralink presentation, July 2019",
        "neuralink",
        "2019-07-16",
        False,
        "First human implant occurred January 2024, over three years late. FDA initially rejected the application in 2022 citing safety concerns. Approved in May 2023.",
        "FDA records, Neuralink announcements",
    ),
    (
        "Neuralink will allow people to communicate telepathically and stream music directly to their brain",
        "Neuralink presentation, Joe Rogan podcast, 2019-2020",
        "neuralink",
        "2019-07-16",
        False,
        "First human patient (Noland Arbaugh, 2024) demonstrated cursor control only. Impressive for a BCI but nowhere near telepathy or music streaming. Some threads retracted from brain, reducing functionality.",
        "Neuralink patient updates, medical reports",
    ),
    (
        "Neuralink will solve blindness and paralysis",
        "Multiple presentations, 2019-2022",
        "neuralink",
        "2020-08-28",
        False,
        "First patient showed promising cursor control for quadriplegia. Blindness device (Blindsight) received FDA breakthrough designation in 2024 but has not restored sight in any patient. Very early stage.",
        "FDA breakthrough device designations, Neuralink updates",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # TESLA - ENERGY / SOLAR
    # ═══════════════════════════════════════════════════════════════════
    (
        "Solar Roof tiles will be cheaper than a regular roof even before energy savings",
        "Solar Roof unveil, October 2016",
        "energy",
        "2016-10-28",
        False,
        "Solar Roof installations cost $50K-$100K+, significantly more expensive than conventional roofing ($10K-$20K). Production scaled very slowly. Multiple customer complaints about delays and cost overruns.",
        "Consumer reports, Tesla Energy pricing",
    ),
    (
        "Tesla Energy will become bigger than Tesla's automotive business",
        "Multiple earnings calls, 2021-2022",
        "energy",
        "2021-07-26",
        False,
        "Tesla Energy revenue was ~$6B in 2023 vs. ~$78B automotive. Energy growing fast (Megapack) but still <10% of total revenue. Claim not close to reality as of 2025.",
        "Tesla annual reports",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # PERSONAL / GENERAL CLAIMS
    # ═══════════════════════════════════════════════════════════════════
    (
        "I work 120 hours a week and sleep on the factory floor",
        "Multiple interviews, 2018",
        "personal_conduct",
        "2018-08-16",
        False,
        "While Musk did sleep at Tesla factories during Model 3 ramp, the 120-hour claim (17+ hours/day, 7 days/week) is physically implausible. He simultaneously ran SpaceX, Neuralink, and Boring Company, and was active on social media constantly.",
        "Interview transcripts, social media activity",
    ),
    (
        "I will sell almost all physical possessions and own no house",
        "Tweet, May 2020",
        "personal_conduct",
        "2020-05-01",
        False,
        "Sold several California homes but reportedly lived in a ~$50K Boxabl tiny house in Texas, then at friends' properties. However, has access to extensive corporate resources, private jets, and reportedly still uses large properties. Distinction between ownership and access is semantic.",
        "Property records, media investigations",
    ),
    (
        "Tesla stock price is too high",
        "Tweet, May 2020",
        "financial",
        "2020-05-01",
        False,
        "Stock dropped ~10% on the tweet. But Musk continued to tout Tesla's value, approved stock splits, and Tesla market cap grew to over $1T by 2021. Used stock as collateral for Twitter acquisition.",
        "TSLA stock history, SEC filings",
    ),
    (
        "Am considering taking Tesla private at $420. Funding secured.",
        "Tweet, August 2018",
        "financial",
        "2018-08-07",
        False,
        "Funding was not secured. SEC charged Musk with fraud. Settled for $20M fine each for Musk and Tesla, plus Musk stepped down as chairman. Tesla remained public.",
        "SEC complaint, settlement agreement",
    ),
    (
        "I will personally go to Mars, maybe I will die there",
        "Multiple interviews, Axios on HBO, 2018",
        "spacex",
        "2018-11-25",
        False,
        "No personal Mars trip planned or attempted as of 2026. Starship still in Earth-orbit testing phase. Musk turned 54 in 2025; timeline increasingly challenging.",
        "SpaceX development status",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # THINGS HE DELIVERED ON
    # ═══════════════════════════════════════════════════════════════════
    (
        "Tesla will build a Gigafactory that produces more lithium-ion batteries than the rest of the world combined",
        "Gigafactory announcement, 2014",
        "production",
        "2014-02-26",
        True,
        "Gigafactory Nevada (opened 2016) became one of the world's largest battery plants. While 'more than rest of world combined' was an overstatement, Tesla/Panasonic production at scale was achieved. Additional Gigafactories built in Shanghai, Berlin, Austin.",
        "Tesla Gigafactory production reports",
    ),
    (
        "SpaceX Dragon will deliver cargo to the International Space Station under NASA contract",
        "SpaceX announcements, 2012",
        "spacex",
        "2012-05-22",
        True,
        "Dragon successfully delivered cargo to ISS starting May 2012. Became a reliable workhorse. Crew Dragon subsequently flew astronauts starting May 2020, ending US reliance on Russian Soyuz.",
        "NASA CRS mission records",
    ),
    (
        "Tesla will build the world's largest battery in South Australia in 100 days or it's free",
        "Twitter bet with Mike Cannon-Brookes, March 2017",
        "energy",
        "2017-03-10",
        True,
        "Hornsdale Power Reserve (100MW/129MWh) completed in approximately 60 days, well within the deadline. Saved South Australia ~$40M in first year of operation.",
        "SA government records, Neoen reports",
    ),
    (
        "Tesla will achieve profitability and positive free cash flow",
        "Multiple earnings calls, 2018-2019",
        "financial",
        "2019-01-30",
        True,
        "Tesla became consistently profitable from Q3 2019 onward. Joined S&P 500 in December 2020. Generated $4.4B net income in 2022 (peak).",
        "Tesla quarterly earnings, S&P index records",
    ),
    (
        "Tesla will open-source all its patents to accelerate EV adoption",
        "Blog post, June 2014",
        "production",
        "2014-06-12",
        True,
        "Tesla published its patent portfolio under an open-source pledge in 2014. Other manufacturers could use Tesla patents without fear of lawsuits, provided reciprocity. Genuine industry contribution.",
        "Tesla blog, patent pledge",
    ),
    (
        "SpaceX Crew Dragon will fly NASA astronauts to the ISS",
        "NASA Commercial Crew contract, 2014",
        "spacex",
        "2014-09-16",
        True,
        "Demo-2 mission (May 30, 2020) carried Doug Hurley and Bob Behnken to ISS. First crewed orbital launch from US soil since Space Shuttle. Regular crew rotation flights followed.",
        "NASA mission records",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # DOGE / GOVERNMENT
    # ═══════════════════════════════════════════════════════════════════
    (
        "DOGE will cut $2 trillion in federal government spending",
        "Campaign events and interviews, 2024",
        "governance",
        "2024-08-12",
        False,
        "DOGE (Department of Government Efficiency) established January 2025. Initial claims revised down from $2T to much smaller figures. Actual verified savings disputed. Musk's own target reportedly revised to $1T, then lower. Courts blocked several cuts.",
        "DOGE announcements, federal court rulings, CBO analysis",
    ),
    (
        "Government efficiency reforms will be completed and I will leave DOGE by July 4, 2025",
        "Multiple statements, early 2025",
        "governance",
        "2025-01-20",
        False,
        "Musk remained involved past the stated deadline. DOGE activities faced extensive legal challenges. Multiple federal judges issued injunctions against DOGE-directed cuts. Many terminated employees ordered reinstated.",
        "Federal court orders, executive branch records",
    ),
    (
        "Tesla will deploy a fully autonomous humanoid robot, Optimus, that does useful work",
        "Tesla AI Day, August 2021",
        "product_delivery",
        "2021-08-19",
        False,
        "Optimus prototype revealed in 2022 (first version could barely walk). Gen 2 (2023) improved but still teleoperated for demos. No commercial deployment. No useful autonomous work performed as of 2026.",
        "Tesla AI Day recordings, demo analysis",
    ),
    (
        "Tesla insurance will be a major part of the business and much cheaper because Teslas are safer",
        "Earnings calls, 2019-2020",
        "financial",
        "2019-04-24",
        False,
        "Tesla Insurance launched in limited states. Not cheaper for most drivers. Many Tesla owners reported high premiums due to expensive repairs. Insurance remained a tiny fraction of Tesla revenue.",
        "Tesla financial reports, consumer reports on insurance costs",
    ),
    (
        "OpenAI should remain open-source and nonprofit, focused on benefiting humanity",
        "OpenAI founding principles co-authored by Musk, 2015",
        "governance",
        "2015-12-11",
        False,
        "Musk departed OpenAI board in 2018. OpenAI transitioned to 'capped-profit' model (2019), then moved toward full for-profit (2024). Musk sued OpenAI in 2024 alleging breach of founding mission, but had previously tried to take control himself.",
        "OpenAI charter, court filings (Musk v. Altman)",
    ),
]

print("=" * 70)
print("SAY/DO POC: Elon Musk Contradiction Index")
print("=" * 70)
print()

# Track all statements
print("PHASE 1: Tracking statements...")
print("-" * 40)
statement_ids = []
for stmt, source, category, date, _, _, _ in DATA:
    result = engine.track_statement(
        entity_name=ENTITY,
        statement=stmt,
        source=source,
        category=category,
        entity_type=ENTITY_TYPE,
        statement_date=date,
    )
    statement_ids.append(result["node_id"])
    print(f"  [tracked] {stmt[:70]}...")

print(f"\n  Total statements tracked: {len(statement_ids)}")

# Resolve outcomes
print("\nPHASE 2: Resolving outcomes...")
print("-" * 40)
for i, (stmt, source, category, date, followed, outcome, evidence) in enumerate(DATA):
    result = engine.resolve_outcome(
        entity_name=ENTITY,
        statement_id=statement_ids[i],
        followed_through=followed,
        outcome_detail=outcome,
        evidence=evidence,
    )
    icon = "Y" if followed else "N"
    score = result.get("contradiction_score", 0.0)
    print(f"  [{icon}] {stmt[:55]}... score={score:.3f}")

print(f"\n  Outcomes resolved: {len(DATA)}")

# Generate profile
print("\nPHASE 3: Contradiction Profile")
print("=" * 70)
profile = engine.get_entity_profile(ENTITY)

print(f"  Entity:              {profile['entity_name']}")
print(f"  Type:                {profile['entity_type']}")
print(f"  Contradiction Score: {profile['contradiction_score']:.3f}")
print(f"  Follow-Through Rate: {profile['follow_through_rate']:.0%}")
print(f"  Total Statements:    {profile['total_statements']}")
print(f"  Resolved:            {profile['resolved_statements']}")
print(f"  Pending:             {profile['pending_statements']}")
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

# Top contradictions
print("\nPHASE 4: Top Contradictions")
print("=" * 70)
contradictions = engine.get_entity_contradictions(ENTITY, min_score=0.0)
for i, c in enumerate(contradictions[:20], 1):
    print(f"  {i}. [score={c['score']:.3f}] {c['summary'][:100]}")

# Predictions
print("\nPHASE 5: Follow-Through Prediction")
print("=" * 70)
from omega.saydo.prediction import predict_followthrough

test_statements = [
    ("Tesla robotaxis will be fully operational in major US cities by end of year", "autonomy"),
    ("Starship will land on Mars within two years", "spacex"),
    ("X will become a profitable super-app with payments", "twitter"),
    ("Tesla will produce a $25,000 electric vehicle", "product_delivery"),
    ("SpaceX will successfully launch and recover Starship on next attempt", "spacex"),
    ("Neuralink will cure blindness within five years", "neuralink"),
]

for stmt, cat in test_statements:
    pred = predict_followthrough(ENTITY, stmt, cat)
    print(f"\n  Statement: \"{stmt}\"")
    print(f"  Category:    {cat}")
    print(f"  Probability: {pred['probability']:.1%}")
    print(f"  Confidence:  {pred['confidence']:.1%}")
    for r in pred["reasoning"]:
        print(f"    - {r}")

# ──────────────────────────────────────────────────────────────────────
# COMPARISON SUMMARY (if Trump data exists)
# ──────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("POC COMPLETE")
print("=" * 70)
