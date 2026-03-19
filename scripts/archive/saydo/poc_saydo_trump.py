#!/usr/bin/env python3
"""Say/Do POC: Donald Trump Contradiction Index.

Populates the Say/Do engine with well-documented public statements and
their known outcomes, then generates the full contradiction profile.

All statements are sourced from public record (speeches, tweets, press
conferences, policy outcomes). This is an accountability tool for
public figures using verifiable facts.
"""

import sys
from pathlib import Path

# Ensure omega is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omega.sqlite_store import SQLiteStore
from omega.saydo.engine import get_saydo_engine, _normalize_entity, _engine_instance
import omega.saydo.engine as eng_mod
import omega.bridge as bridge

# Use a dedicated test DB so we don't pollute the main store
DB_PATH = Path(__file__).parent.parent / "data" / "poc_saydo_trump.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

store = SQLiteStore(db_path=str(DB_PATH))
bridge._store_instance = store
eng_mod._engine_instance = None  # Reset singleton

engine = get_saydo_engine()

ENTITY = "Donald Trump"
ENTITY_TYPE = "politician"

# ──────────────────────────────────────────────────────────────────────
# STATEMENTS + OUTCOMES
# Each tuple: (statement, source, category, date, followed_through, outcome_detail, evidence)
# ──────────────────────────────────────────────────────────────────────

DATA = [
    # --- IMMIGRATION ---
    (
        "I will build a great wall on the southern border, and Mexico will pay for the wall",
        "Campaign announcement speech, June 2015",
        "immigration",
        "2015-06-16",
        False,
        "Wall partially built using US taxpayer funds. Mexico never paid. Congress appropriated ~$15B via executive action and budget fights.",
        "GAO reports, Congressional budget records",
    ),
    # --- HEALTHCARE ---
    (
        "We're going to repeal and replace Obamacare with something much better and much less expensive",
        "Campaign rally, multiple occasions 2015-2016",
        "healthcare",
        "2016-03-01",
        False,
        "ACA repeal failed in Senate (McCain thumbs-down vote, July 2017). No replacement legislation passed. ACA remains law.",
        "Senate vote record, July 28 2017",
    ),
    # --- ECONOMY / DEBT ---
    (
        "We can eliminate the $19 trillion national debt over a period of eight years",
        "Washington Post interview, April 2016",
        "economy",
        "2016-04-02",
        False,
        "National debt increased from $19.9T to $27.7T during single term (2017-2021). Grew by ~$7.8T.",
        "US Treasury Department debt records",
    ),
    (
        "I will be the greatest jobs president that God ever created",
        "Campaign announcement speech, June 2015",
        "economy",
        "2015-06-16",
        False,
        "Pre-COVID job growth continued Obama-era trend. COVID caused loss of ~22M jobs. Left office with 3M fewer jobs than when inaugurated (net negative, first president since Hoover).",
        "Bureau of Labor Statistics",
    ),
    # --- TAX RETURNS ---
    (
        "I will release my tax returns when the audit is complete",
        "Multiple press conferences, 2015-2016",
        "transparency",
        "2016-01-01",
        False,
        "Tax returns were never voluntarily released during presidency. Only made public when House Ways and Means Committee obtained them in 2022.",
        "Public record, House Ways and Means Committee",
    ),
    # --- GOLF ---
    (
        "I'm going to be working for you. I'm not going to have time to go play golf",
        "Campaign rally, August 2016",
        "personal_conduct",
        "2016-08-01",
        False,
        "Visited golf courses over 300 times during presidency, often at his own properties. Spent ~$150M in taxpayer funds on golf trips (GAO estimate).",
        "Presidential travel logs, GAO reports",
    ),
    # --- DRAIN THE SWAMP ---
    (
        "We are going to drain the swamp in Washington, D.C.",
        "Campaign rally, October 2016",
        "governance",
        "2016-10-17",
        False,
        "Multiple cabinet members resigned or were fired amid ethics scandals (Price, Pruitt, Zinke). Several associates convicted of federal crimes (Manafort, Stone, Flynn, Bannon). Lobbying waivers granted to former lobbyists joining administration.",
        "DOJ records, ethics office reports",
    ),
    # --- COVID ---
    (
        "It's going to disappear. One day, it's like a miracle, it will disappear",
        "White House press conference, February 2020",
        "public_health",
        "2020-02-27",
        False,
        "COVID-19 killed over 400,000 Americans by end of term (Jan 2021). Did not disappear. Pandemic lasted years globally.",
        "CDC death counts, WHO records",
    ),
    # --- INFRASTRUCTURE ---
    (
        "We will build gleaming new roads, bridges, highways, railways, and waterways all across our land",
        "Inaugural address, January 2017",
        "infrastructure",
        "2017-01-20",
        False,
        "No major infrastructure bill passed during term despite multiple 'infrastructure weeks.' Infrastructure legislation only passed under Biden (2021 Bipartisan Infrastructure Law).",
        "Congressional record",
    ),
    # --- TRADE ---
    (
        "I will withdraw the United States from the Trans-Pacific Partnership",
        "Campaign speech, June 2016",
        "trade",
        "2016-06-28",
        True,
        "Signed executive order withdrawing from TPP on January 23, 2017, his third day in office.",
        "Executive Order, White House records",
    ),
    (
        "I will renegotiate NAFTA",
        "Campaign promise, multiple occasions 2016",
        "trade",
        "2016-06-28",
        True,
        "USMCA (United States-Mexico-Canada Agreement) signed November 2018, ratified January 2020. Replaced NAFTA with updated terms.",
        "USTR records",
    ),
    (
        "Trade wars are good and easy to win",
        "Twitter, March 2018",
        "trade",
        "2018-03-02",
        False,
        "US-China trade war lasted years. US trade deficit with China grew from $375B (2017) to $419B (2018). Farmers required $28B in bailouts. No Phase 2 deal materialized.",
        "Census Bureau trade data, USDA records",
    ),
    # --- FOREIGN POLICY ---
    (
        "I will move the American embassy in Israel to Jerusalem",
        "AIPAC speech, March 2016",
        "foreign_policy",
        "2016-03-21",
        True,
        "Embassy moved to Jerusalem on May 14, 2018. Recognized Jerusalem as capital of Israel.",
        "State Department records",
    ),
    (
        "I alone can fix it",
        "RNC acceptance speech, July 2016",
        "governance",
        "2016-07-21",
        False,
        "Government shutdown lasted 35 days (Dec 2018-Jan 2019), longest in US history. COVID response widely criticized. Left office after Capitol breach and second impeachment.",
        "Congressional record, public record",
    ),
    (
        "We will achieve complete denuclearization of the Korean Peninsula",
        "Singapore summit statement, June 2018",
        "foreign_policy",
        "2018-06-12",
        False,
        "North Korea continued nuclear weapons development. Satellite imagery showed expanded facilities. Hanoi summit (Feb 2019) collapsed with no deal. No denuclearization achieved.",
        "IAEA reports, satellite imagery analysis",
    ),
    # --- JUDICIARY ---
    (
        "I will appoint conservative justices to the Supreme Court",
        "Campaign promise, multiple occasions 2016",
        "judiciary",
        "2016-05-18",
        True,
        "Appointed three Supreme Court justices: Gorsuch (2017), Kavanaugh (2018), Barrett (2020). Shifted court to 6-3 conservative majority.",
        "Supreme Court records",
    ),
    # --- ENVIRONMENT ---
    (
        "I will pull the United States out of the Paris Climate Agreement",
        "Campaign statement, May 2016",
        "environment",
        "2016-05-26",
        True,
        "Announced withdrawal from Paris Agreement on June 1, 2017. US formally exited November 4, 2020.",
        "State Department, UN records",
    ),
    (
        "I will bring back the coal industry and save coal jobs",
        "Campaign rally, West Virginia, May 2016",
        "economy",
        "2016-05-05",
        False,
        "Coal production continued declining. Coal employment fell from 51,000 (2017) to 42,000 (2020). Multiple coal companies filed for bankruptcy during his term.",
        "EIA data, BLS employment figures",
    ),
    # --- ECONOMY ---
    (
        "We will cut taxes for the middle class and for businesses",
        "Campaign promise, 2016",
        "economy",
        "2016-09-01",
        True,
        "Tax Cuts and Jobs Act signed December 2017. Cut corporate rate from 35% to 21%. Individual rates also reduced, though benefits skewed to higher incomes per CBO analysis.",
        "Public Law 115-97, CBO analysis",
    ),
    (
        "I will impose tariffs on China to bring back American manufacturing",
        "Campaign speech, multiple occasions 2016",
        "trade",
        "2016-07-01",
        True,
        "Imposed multiple rounds of tariffs on Chinese goods totaling ~$370B. However, manufacturing job gains were modest and reversed by 2019 before COVID.",
        "USTR tariff schedules, BLS data",
    ),
    # --- IMMIGRATION CONTINUED ---
    (
        "We will immediately deport 11 million illegal immigrants",
        "Campaign rally, multiple occasions 2015",
        "immigration",
        "2015-08-15",
        False,
        "ICE deportations averaged ~226K/year during Trump term, similar to Obama-era levels. Nowhere near 11 million. Logistically impossible as claimed.",
        "ICE ERO annual reports",
    ),
    (
        "I am calling for a total and complete shutdown of Muslims entering the United States",
        "Campaign statement, December 2015",
        "immigration",
        "2015-12-07",
        False,
        "Travel ban (EO 13769, later revised) restricted travel from several Muslim-majority countries but was not a total Muslim ban. Supreme Court upheld revised version (Trump v. Hawaii, 2018). Did not cover all Muslim countries.",
        "Executive Orders, Supreme Court ruling",
    ),
    (
        "We will end catch and release",
        "Campaign promise, 2016",
        "immigration",
        "2016-08-31",
        False,
        "Catch-and-release continued throughout presidency due to legal constraints (Flores settlement), facility capacity limits, and court orders. Zero-tolerance policy (2018) caused family separation crisis but catch-and-release persisted.",
        "DHS records, court orders",
    ),
    # --- GOVERNANCE ---
    (
        "I will impose a five-year ban on executive branch officials lobbying after leaving government",
        "Campaign ethics plan, October 2016",
        "governance",
        "2016-10-18",
        False,
        "Signed EO with lobbying restrictions but included numerous waivers. Revoked the order on his last day in office (Jan 20, 2021), freeing all former officials to lobby immediately.",
        "Executive Orders, White House records",
    ),
    (
        "I will push for a constitutional amendment to impose term limits on all members of Congress",
        "Gettysburg speech, October 2016",
        "governance",
        "2016-10-22",
        False,
        "No term limits amendment was ever introduced by the administration. No legislative effort was made. Requires two-thirds of both chambers plus ratification by 38 states.",
        "Congressional record",
    ),
    (
        "I will impose a hiring freeze on all federal employees",
        "Contract with the American Voter, 2016",
        "governance",
        "2016-10-22",
        False,
        "Hiring freeze signed Jan 23, 2017 but lifted April 2017 (lasted ~3 months). Federal workforce grew from 2.09M to 2.18M during his term.",
        "OPM FedScope data",
    ),
    # --- MILITARY / DEFENSE ---
    (
        "I will rebuild our military and make it so strong no one will mess with us",
        "Campaign rally, multiple occasions 2016",
        "military",
        "2016-09-07",
        True,
        "Defense spending increased from $606B (FY2017) to $740B (FY2021). Signed largest defense budgets in US history. Created Space Force as sixth branch.",
        "DOD budget records, National Defense Authorization Acts",
    ),
    (
        "I will create a Space Force as a new branch of the military",
        "Announcement, June 2018",
        "military",
        "2018-06-18",
        True,
        "United States Space Force established December 20, 2019 as the sixth branch of the US Armed Forces via National Defense Authorization Act for FY2020.",
        "Public Law 116-92",
    ),
    (
        "I will take care of our veterans. They will not be forgotten",
        "Campaign rally, multiple occasions 2016",
        "military",
        "2016-07-11",
        True,
        "Signed VA MISSION Act (2018) expanding private healthcare access for veterans. Signed VA Accountability Act (2017). VA budget increased. However, VA still faced staffing shortages.",
        "Public Laws 115-46, 115-182",
    ),
    (
        "I will defeat ISIS quickly and knock the hell out of them",
        "Campaign rally, multiple occasions 2015-2016",
        "military",
        "2015-11-12",
        True,
        "ISIS territorial caliphate fell by March 2019. Last major stronghold (Baghouz) captured. However, ISIS remained active as an insurgency and resumed attacks by 2020.",
        "DOD briefings, CENTCOM reports",
    ),
    (
        "I will bring troops home from Afghanistan and end endless wars",
        "Multiple statements, 2019-2020",
        "military",
        "2019-01-02",
        False,
        "Signed Doha Agreement with Taliban (Feb 2020) but troop withdrawal not completed during term. Left ~2,500 troops. Full withdrawal occurred under Biden (Aug 2021).",
        "Doha Agreement, DOD troop figures",
    ),
    # --- HEALTHCARE CONTINUED ---
    (
        "I will protect people with pre-existing conditions",
        "Multiple rally statements, 2018-2020",
        "healthcare",
        "2018-10-15",
        False,
        "Administration supported Texas v. California lawsuit seeking to strike down the entire ACA, which included pre-existing condition protections. No alternative legislation with such protections was proposed.",
        "DOJ court filings, Congressional record",
    ),
    (
        "We will have a beautiful healthcare plan that will be ready in two weeks",
        "Multiple press conferences, 2017-2020",
        "healthcare",
        "2020-07-19",
        False,
        "The 'two weeks' healthcare plan was promised repeatedly from 2017 to 2020. No comprehensive healthcare plan was ever released. Became a running joke in political media.",
        "Press conference transcripts, media tracking",
    ),
    (
        "We will negotiate drug prices down to save billions",
        "Campaign promise, 2016; reiterated multiple times",
        "healthcare",
        "2016-01-26",
        False,
        "Executive orders on drug pricing signed in 2020 were largely symbolic. Most Favored Nation rule finalized but immediately challenged and never implemented. No legislation passed. Medicare was still prohibited from negotiating prices (that changed under Biden's IRA in 2022).",
        "CMS records, Congressional record",
    ),
    # --- TRANSPARENCY CONTINUED ---
    (
        "This will be the most transparent administration in history",
        "Multiple statements, 2017",
        "transparency",
        "2017-01-25",
        False,
        "Refused to release tax returns. Restricted press access. Fired inspectors general. Defied congressional subpoenas. Used personal phones for government business. White House visitor logs not released.",
        "Press freedom indices, Congressional investigations",
    ),
    (
        "I will testify under oath to Robert Mueller, I would love to do it",
        "Press gaggle, January 2018",
        "transparency",
        "2018-01-24",
        False,
        "Never testified in person or under oath. Submitted written answers only (November 2018), many of which stated 'I do not recall.' Mueller noted the limitations in his final report.",
        "Mueller Report, Vol. II, Appendix C",
    ),
    # --- PERSONAL CONDUCT ---
    (
        "I will donate my entire presidential salary",
        "Campaign trail, 2016",
        "personal_conduct",
        "2016-09-15",
        True,
        "Donated $400K annual salary each quarter to various government agencies (National Park Service, SBA, HHS, etc.). Documented via quarterly checks.",
        "White House press releases, agency confirmations",
    ),
    (
        "I won't have time to take vacations. There's so much work to be done",
        "Interview, 2015",
        "personal_conduct",
        "2015-06-23",
        False,
        "Spent significant time at Mar-a-Lago, Bedminster, and other properties. GAO found ~$150M in travel costs for trips to his properties in first few years alone.",
        "GAO reports, presidential travel logs",
    ),
    (
        "I will sue every one of the women who accused me of sexual misconduct",
        "Campaign rally, October 2016",
        "personal_conduct",
        "2016-10-22",
        False,
        "Never filed lawsuits against accusers. Multiple accusers' cases against him proceeded. E. Jean Carroll won defamation and battery cases against him in 2023-2024.",
        "Court records",
    ),
    # --- CRIMINAL JUSTICE ---
    (
        "I will be tough on crime and support law enforcement 100%",
        "Campaign rally, multiple occasions 2016",
        "governance",
        "2016-07-18",
        False,
        "Signed First Step Act (Dec 2018) reducing sentences, which contradicted 'tough on crime' rhetoric. Pardoned associates convicted of federal crimes (Flynn, Manafort, Stone, Bannon). Commuted Roger Stone's sentence.",
        "Public Law 115-391, DOJ pardon records",
    ),
    # --- SOCIAL SECURITY ---
    (
        "I will save Social Security and Medicare without any cuts",
        "Campaign promise, multiple occasions 2015-2016",
        "economy",
        "2016-04-18",
        False,
        "FY2021 budget proposed $850B in cuts to Medicare over 10 years. Signed payroll tax deferral in 2020 which social security trustees warned could accelerate insolvency. Social Security trust fund depletion timeline accelerated.",
        "OMB budget proposals, Social Security Trustees report",
    ),
    # --- EDUCATION ---
    (
        "I will get rid of Common Core and bring education to a local level",
        "Campaign promise, 2016",
        "education",
        "2016-02-17",
        False,
        "Common Core is a state-level initiative, not federal. The president has no direct authority to eliminate it. States continued using Common Core or derivatives. Some states rebranded but kept the same standards.",
        "Education policy records",
    ),
    # --- TECH ---
    (
        "We will bring back jobs from China and Apple will build their plants in the United States",
        "Campaign rally, multiple occasions 2016",
        "economy",
        "2016-01-18",
        False,
        "Apple did not move iPhone manufacturing to the US. Announced $1B fund and Austin campus but iPhone production remained in China. Foxconn Wisconsin plant (promised 13K jobs) scaled down dramatically to small innovation center.",
        "Apple financial filings, Foxconn/Mount Pleasant records",
    ),
    # --- FOREIGN POLICY CONTINUED ---
    (
        "I will cancel the Iran nuclear deal on day one",
        "AIPAC speech, March 2016",
        "foreign_policy",
        "2016-03-21",
        True,
        "Withdrew from JCPOA on May 8, 2018 (not day one, but did withdraw). Reimposed sanctions on Iran. Completed.",
        "State Department announcement, Executive Order",
    ),
    (
        "I will make our NATO allies pay their fair share",
        "Campaign rally, multiple occasions 2016",
        "foreign_policy",
        "2016-04-27",
        True,
        "Persistent pressure led to NATO allies increasing defense spending. By 2020, 10 allies met the 2% GDP target (up from 4 in 2016). Overall NATO spending increased ~$130B.",
        "NATO annual reports, defense expenditure data",
    ),
    (
        "I will bring peace to the Middle East",
        "Multiple statements, 2017-2020",
        "foreign_policy",
        "2017-05-22",
        False,
        "Abraham Accords (2020) normalized relations between Israel and UAE/Bahrain/Morocco. However, Israeli-Palestinian conflict was not resolved. October 7, 2023 Hamas attack and subsequent war demonstrated peace not achieved.",
        "Abraham Accords, State Department",
    ),
    # --- INFRASTRUCTURE / TECH ---
    (
        "We will have so much winning, you'll get tired of winning",
        "Campaign rally, multiple occasions 2015-2016",
        "governance",
        "2015-09-09",
        False,
        "Lost House majority in 2018 midterms. Impeached twice (2019, 2021). Lost popular vote in both 2016 and 2020. Lost 2020 presidential election. Multiple legislative priorities failed (healthcare, infrastructure, immigration reform).",
        "Election results, Congressional record",
    ),
    (
        "I will not cut Medicaid",
        "Campaign promise via Twitter, May 2015",
        "healthcare",
        "2015-05-07",
        False,
        "Every budget proposal included significant Medicaid cuts. Supported AHCA which would have cut Medicaid by $880B over 10 years. Approved Medicaid work requirements that caused coverage losses in Arkansas.",
        "OMB budget proposals, CBO analysis of AHCA",
    ),
    (
        "I will release my beautiful healthcare plan within the first 60 days",
        "Interview with The Washington Post, early 2016",
        "healthcare",
        "2016-02-01",
        False,
        "No healthcare plan released in first 60 days or any subsequent period. The 'two weeks' promise was repeated over 30 times throughout his presidency.",
        "Interview transcripts, media tracking",
    ),
    (
        "I will use the Defense Production Act and we will have millions of tests available very soon",
        "Press conference, March 2020",
        "public_health",
        "2020-03-18",
        False,
        "Testing remained inadequate for months. US lagged behind other developed nations in per-capita testing through spring/summer 2020. DPA was invoked belatedly and selectively.",
        "CDC testing data, FEMA records",
    ),
]

print("=" * 70)
print("SAY/DO POC: Donald Trump Contradiction Index")
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
    status = "tracked"
    print(f"  [{status}] {stmt[:70]}...")

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

# Search contradictions
print("\nPHASE 4: Top Contradictions")
print("=" * 70)
contradictions = engine.get_entity_contradictions(ENTITY, min_score=0.0)
for i, c in enumerate(contradictions, 1):
    print(f"  {i}. [score={c['score']:.3f}] {c['summary'][:100]}")

# Prediction
print("\nPHASE 5: Follow-Through Prediction")
print("=" * 70)
from omega.saydo.prediction import predict_followthrough

test_statements = [
    ("I will secure the border completely", "immigration"),
    ("I will cut government spending dramatically", "economy"),
    ("I will release my financial records", "transparency"),
    ("I will appoint conservative judges", "judiciary"),
]

for stmt, cat in test_statements:
    pred = predict_followthrough(ENTITY, stmt, cat)
    print(f"\n  Statement: \"{stmt}\"")
    print(f"  Category:    {cat}")
    print(f"  Probability: {pred['probability']:.1%}")
    print(f"  Confidence:  {pred['confidence']:.1%}")
    for r in pred["reasoning"]:
        print(f"    - {r}")

print("\n" + "=" * 70)
print("POC COMPLETE")
print("=" * 70)
