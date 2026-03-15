#!/usr/bin/env python3
"""Say/Do POC: Joe Biden Contradiction Index.

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
DB_PATH = Path(__file__).parent.parent / "data" / "poc_saydo_biden.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

store = SQLiteStore(db_path=str(DB_PATH))
bridge._store_instance = store
eng_mod._engine_instance = None  # Reset singleton

engine = get_saydo_engine()

ENTITY = "Joe Biden"
ENTITY_TYPE = "politician"

# ──────────────────────────────────────────────────────────────────────
# STATEMENTS + OUTCOMES
# Each tuple: (statement, source, category, date, followed_through, outcome_detail, evidence)
# ──────────────────────────────────────────────────────────────────────

DATA = [
    # --- ECONOMY / COVID RELIEF ---
    (
        "We need a $1.9 trillion American Rescue Plan to get COVID relief to the American people",
        "Press conference, January 2021",
        "economy",
        "2021-01-14",
        True,
        "American Rescue Plan signed into law March 11, 2021. Included $1,400 stimulus checks, unemployment benefits extension, child tax credit expansion, vaccine funding.",
        "Public Law 117-2",
    ),
    (
        "I will get 200 million COVID vaccine doses administered in my first 100 days",
        "Press conference, January 2021",
        "public_health",
        "2021-01-25",
        True,
        "Exceeded target. Achieved 220 million doses by April 30, 2021 (day 100). Later revised upward to 300 million and surpassed that as well.",
        "CDC vaccination data",
    ),
    # --- INFRASTRUCTURE ---
    (
        "We will pass a historic bipartisan infrastructure bill to rebuild America",
        "Campaign promise, 2020",
        "infrastructure",
        "2020-07-09",
        True,
        "Infrastructure Investment and Jobs Act signed November 15, 2021. $1.2 trillion package for roads, bridges, broadband, clean water, electric grid. Passed with bipartisan support (19 GOP Senators).",
        "Public Law 117-58",
    ),
    # --- BUILD BACK BETTER ---
    (
        "We will pass the Build Back Better plan worth over $2 trillion for climate, childcare, and healthcare",
        "Campaign promise, 2020; reiterated 2021",
        "economy",
        "2020-07-14",
        False,
        "Build Back Better failed to pass Senate (Manchin, Sinema opposition). Scaled-down version became Inflation Reduction Act ($437B) in August 2022. Lost childcare, free community college, expanded Medicare provisions.",
        "Congressional record, Senate votes",
    ),
    # --- CLIMATE ---
    (
        "On day one, I will rejoin the Paris Climate Agreement",
        "Campaign promise, 2020",
        "environment",
        "2020-06-04",
        True,
        "Signed executive order to rejoin Paris Agreement on January 20, 2021 (first day in office). US formally rejoined February 19, 2021.",
        "Executive Order 13990, UN records",
    ),
    (
        "I will end new oil and gas drilling on federal lands",
        "Campaign debate, March 2020",
        "environment",
        "2020-03-15",
        False,
        "Paused new leases initially but court ordered resumption. Approved Willow Project in Alaska (2023). Oil production reached record highs during his term. Did not end drilling.",
        "DOI records, EIA production data",
    ),
    (
        "We will invest $370 billion in climate and clean energy through the Inflation Reduction Act",
        "State of the Union, 2023",
        "environment",
        "2022-08-01",
        True,
        "Inflation Reduction Act signed August 16, 2022 with $369B in climate spending over 10 years. Largest climate investment in US history. Includes EV tax credits, solar/wind incentives.",
        "Public Law 117-169",
    ),
    # --- MINIMUM WAGE ---
    (
        "I will raise the federal minimum wage to $15 per hour",
        "Campaign promise, 2020",
        "economy",
        "2020-04-27",
        False,
        "Federal minimum wage remains $7.25. Legislation failed in Senate (March 2021, 58-42 vote). Did sign executive order raising minimum wage for federal contractors to $15/hr (April 2021).",
        "Congressional record, Executive Order 14026",
    ),
    # --- IMMIGRATION ---
    (
        "I will send comprehensive immigration reform to Congress on day one",
        "Campaign promise, 2020",
        "immigration",
        "2020-12-22",
        False,
        "US Citizenship Act introduced January 2021 but never passed. No floor vote in either chamber. Immigration reform remains stalled. Border policies remained contentious throughout term.",
        "Congressional record",
    ),
    (
        "We will restore the Deferred Action for Childhood Arrivals program",
        "Campaign promise, 2020",
        "immigration",
        "2020-06-18",
        True,
        "Signed executive order on day one protecting DACA. DOJ defended program in courts. DHS issued final rule preserving DACA (August 2022). Program remains active.",
        "Executive Order 13993, Federal Register Vol 87",
    ),
    (
        "I will end the border wall construction",
        "Campaign promise, 2020",
        "immigration",
        "2020-08-05",
        False,
        "Paused construction initially but later authorized continuation in some areas. CBP filled gaps citing operational needs. Biden admin used some border wall funds Congress had appropriated.",
        "DHS records, CBP reports",
    ),
    (
        "We will secure the border and fix the broken immigration system",
        "State of the Union, multiple years",
        "immigration",
        "2023-02-07",
        False,
        "Border encounters hit record highs (over 2 million in FY2022, FY2023). Remain in Mexico ended, Title 42 ended May 2023. Immigration policy remained deeply polarized. No comprehensive reform passed.",
        "CBP encounter statistics",
    ),
    # --- HEALTHCARE ---
    (
        "I will protect and expand the Affordable Care Act",
        "Campaign promise, 2020",
        "healthcare",
        "2020-06-25",
        True,
        "Signed executive order strengthening ACA enrollment. American Rescue Plan expanded ACA subsidies. Inflation Reduction Act extended enhanced subsidies through 2025. Uninsured rate dropped.",
        "HHS enrollment reports",
    ),
    (
        "I will create a public option for healthcare",
        "Campaign promise, 2020",
        "healthcare",
        "2020-04-09",
        False,
        "No public option legislation passed or seriously pursued. Democratic caucus lacked votes (Manchin opposed). Proposal did not advance beyond discussion phase.",
        "Congressional record",
    ),
    (
        "I will allow Medicare to negotiate drug prices",
        "Campaign promise, 2020",
        "healthcare",
        "2020-03-23",
        True,
        "Inflation Reduction Act (August 2022) allowed Medicare to negotiate prices on select drugs starting 2026. First 10 drugs selected for negotiation announced August 2023. Historic change to Medicare.",
        "Public Law 117-169, CMS announcements",
    ),
    (
        "I will lower prescription drug costs for seniors",
        "Campaign promise, 2020",
        "healthcare",
        "2020-05-11",
        True,
        "Inflation Reduction Act capped out-of-pocket insulin at $35/month for Medicare recipients and capped total annual drug costs at $2,000 starting 2025. Significant cost reductions achieved.",
        "Public Law 117-169, CMS implementation",
    ),
    # --- AFGHANISTAN ---
    (
        "We will end the war in Afghanistan and bring our troops home",
        "Campaign promise, 2020",
        "military",
        "2020-02-29",
        True,
        "Withdrew all US troops by August 31, 2021, ending 20-year war. However, withdrawal was chaotic. Kabul fell to Taliban August 15. Abbey Gate bombing killed 13 US service members. Evacuation left allies behind.",
        "DOD records, news archives",
    ),
    # --- SUPREME COURT ---
    (
        "I will appoint the first Black woman to the Supreme Court",
        "Campaign promise, 2020",
        "governance",
        "2020-02-25",
        True,
        "Nominated Judge Ketanji Brown Jackson to replace Justice Breyer. Confirmed by Senate 53-47 on April 7, 2022. First Black woman Supreme Court justice.",
        "Senate confirmation vote, Supreme Court records",
    ),
    # --- ABORTION / ROE ---
    (
        "I will codify Roe v. Wade into law",
        "State of the Union, 2023",
        "governance",
        "2023-02-07",
        False,
        "Roe overturned by Dobbs decision June 24, 2022. Women's Health Protection Act passed House but failed in Senate (49-51, May 2022). Lacked votes to pass. Not codified.",
        "Supreme Court ruling, Senate vote record",
    ),
    # --- VOTING RIGHTS ---
    (
        "I will pass the John Lewis Voting Rights Act",
        "Campaign promise and State of the Union, 2021-2023",
        "governance",
        "2021-03-17",
        False,
        "Failed in Senate (January 2022, 49-51). Did not overcome filibuster despite Democratic push. Manchin and Sinema opposed filibuster reform needed to pass it.",
        "Senate vote record",
    ),
    # --- STUDENT LOANS ---
    (
        "I will forgive $10,000 in student loan debt for borrowers",
        "Campaign promise, 2020",
        "economy",
        "2020-03-22",
        False,
        "Announced $10K-$20K forgiveness plan (August 2022) but Supreme Court struck it down 6-3 (June 2023). Used alternative SAVE plan and other targeted relief. Original broad plan blocked.",
        "Supreme Court Biden v. Nebraska, 600 U.S. ___ (2023)",
    ),
    (
        "We will provide targeted student loan relief and reform repayment plans",
        "Press conference, 2022",
        "economy",
        "2022-04-06",
        True,
        "Created SAVE plan (income-driven repayment). Provided relief for public service workers, defrauded borrowers, disabled borrowers. Over $130B in targeted relief by 2024 to ~3.6M borrowers.",
        "Department of Education records",
    ),
    # --- CHIPS ACT ---
    (
        "We will pass the CHIPS Act to bring semiconductor manufacturing back to America",
        "State of the Union, 2022",
        "economy",
        "2022-03-01",
        True,
        "CHIPS and Science Act signed August 9, 2022. $52B for semiconductor manufacturing and research. Intel, TSMC, Samsung announced new US fabs. Bipartisan legislation.",
        "Public Law 117-167",
    ),
    # --- GUN REFORM ---
    (
        "I will ban assault weapons and high-capacity magazines",
        "Campaign promise, 2020; reiterated after Uvalde",
        "governance",
        "2020-08-14",
        False,
        "No assault weapons ban passed. Bipartisan Safer Communities Act (June 2022) expanded background checks and red flag laws but did not ban assault weapons. Lacked votes in Congress.",
        "Congressional record, Public Law 117-159",
    ),
    (
        "We will pass the most significant gun safety legislation in 30 years",
        "Press conference, June 2022",
        "governance",
        "2022-06-12",
        True,
        "Bipartisan Safer Communities Act signed June 25, 2022. Enhanced background checks for under-21 buyers, red flag support, mental health funding, closes boyfriend loophole. First major gun law since 1994.",
        "Public Law 117-159",
    ),
    # --- ECONOMY CONTINUED ---
    (
        "We will create millions of good-paying jobs in clean energy and manufacturing",
        "Campaign promise, 2020",
        "economy",
        "2020-07-14",
        True,
        "Unemployment fell from 6.4% (Jan 2021) to 3.7% (Dec 2023). Job growth averaged 400K/month in 2021-2022. Manufacturing added 800K jobs by 2023. Clean energy investments surged after IRA.",
        "Bureau of Labor Statistics",
    ),
    (
        "Inflation is transitory and will come down",
        "Press conference, July 2021",
        "economy",
        "2021-07-19",
        False,
        "Inflation peaked at 9.1% (June 2022), 40-year high. Not transitory. Took Federal Reserve aggressive rate hikes to bring down to ~3% by late 2023. Caused economic pain.",
        "BLS CPI data",
    ),
    # --- TAXES ---
    (
        "No one making under $400,000 will see their taxes go up by a single penny",
        "Campaign promise, 2020",
        "economy",
        "2020-05-22",
        True,
        "Inflation Reduction Act and American Rescue Plan did not raise income taxes on those earning under $400K. Corporate minimum tax (15%) and IRS enforcement provisions did not affect middle class. Promise kept per Tax Policy Center.",
        "Tax Policy Center analysis, IRS records",
    ),
    # --- GUANTANAMO BAY ---
    (
        "I will close the Guantanamo Bay detention facility",
        "Campaign promise, 2020 (also Obama-era promise)",
        "foreign_policy",
        "2020-07-23",
        False,
        "Guantanamo remains open. Biden reviewed closure options but never took action. Population reduced from 40 to 30 detainees but facility operational. Congress blocked transfers.",
        "DOD records, Congressional restrictions",
    ),
    # --- DEATH PENALTY ---
    (
        "I will work to eliminate the federal death penalty",
        "Campaign promise, 2020",
        "governance",
        "2020-07-08",
        False,
        "Instituted informal moratorium, no federal executions during term (Trump admin had executed 13 in final months). But did not formally abolish or commute all death sentences. Legislative effort never materialized.",
        "DOJ records",
    ),
    # --- NATO / FOREIGN POLICY ---
    (
        "We will strengthen NATO and stand with our allies",
        "Campaign promise, 2020; Munich speech 2021",
        "foreign_policy",
        "2021-02-19",
        True,
        "NATO expanded with Finland (April 2023) and Sweden (March 2024). Led coalition supporting Ukraine after Russian invasion (Feb 2022). NATO spending increased. Alliance strengthened significantly.",
        "NATO records, State Department",
    ),
    (
        "We will support Ukraine against Russian aggression",
        "Multiple statements, 2022-2023",
        "foreign_policy",
        "2022-02-24",
        True,
        "Provided over $75B in military, economic, humanitarian aid to Ukraine through 2023. Led international coalition. Shared intelligence. Imposed severe sanctions on Russia.",
        "State Department, DOD records",
    ),
    # --- IRAN ---
    (
        "We will rejoin the Iran nuclear deal and restore diplomacy",
        "Campaign promise, 2020",
        "foreign_policy",
        "2020-09-13",
        False,
        "Negotiations to rejoin JCPOA stalled repeatedly 2021-2023. Iran advanced nuclear program. US did not rejoin deal. Sanctions remained. Iran enriched uranium to near weapons-grade levels.",
        "State Department, IAEA reports",
    ),
    # --- CHINA ---
    (
        "We will compete with China without seeking conflict",
        "Foreign policy speech, 2021",
        "foreign_policy",
        "2021-03-25",
        True,
        "Maintained tariffs on China. Restricted semiconductor exports. Invested in domestic manufacturing (CHIPS Act). Avoided direct military conflict. Managed Taiwan tensions. Competition intensified but no war.",
        "State Department, Commerce Department",
    ),
    # --- INFRASTRUCTURE CONTINUED ---
    (
        "We will ensure every American has access to high-speed internet",
        "Infrastructure plan, 2021",
        "infrastructure",
        "2021-03-31",
        True,
        "Infrastructure law included $65B for broadband expansion. Broadband Equity Access and Deployment (BEAD) program distributing funds to states starting 2023. Rollout ongoing.",
        "Public Law 117-58, NTIA records",
    ),
    # --- POLICE REFORM ---
    (
        "I will sign the George Floyd Justice in Policing Act",
        "Address to joint session, April 2021",
        "governance",
        "2021-04-28",
        False,
        "Passed House (March 2021, 220-212) but failed in Senate. Negotiations between Booker, Scott, Bass collapsed June 2021. No police reform legislation passed. Issued executive order instead (May 2022).",
        "Congressional record, Executive Order 14074",
    ),
    # --- CANCER MOONSHOT ---
    (
        "We will cut the cancer death rate by at least 50% over the next 25 years",
        "State of the Union, 2022",
        "public_health",
        "2022-02-01",
        False,
        "Cancer Moonshot relaunched with ARPA-H funding ($2.5B). Early stages, cannot determine success/failure yet. Goal is long-term (2047). Too early to judge but plan is in motion.",
        "NIH, ARPA-H records",
    ),
    # --- CHILD POVERTY ---
    (
        "We will keep the expanded Child Tax Credit to reduce child poverty",
        "Build Back Better plan, 2021",
        "economy",
        "2021-09-13",
        False,
        "Expanded CTC (monthly payments, fully refundable) enacted in American Rescue Plan expired December 2021. Manchin opposed extension. Child poverty spiked back up in 2022 after dramatic drop in 2021.",
        "Census Bureau poverty data",
    ),
    # --- FREE COMMUNITY COLLEGE ---
    (
        "We will provide two years of free community college",
        "Campaign promise, 2020",
        "education",
        "2020-10-06",
        False,
        "Proposal stripped from Build Back Better due to cost concerns and Manchin opposition. Never passed. Community college remains tuition-based.",
        "Congressional negotiations, media reports",
    ),
    # --- FEDERAL PRISONS ---
    (
        "I will end federal contracts with private prisons",
        "Campaign promise, 2020",
        "governance",
        "2020-07-08",
        True,
        "Signed executive order January 26, 2021 directing DOJ not to renew private prison contracts. Bureau of Prisons phased out contracts. Population in private federal prisons dropped significantly.",
        "Executive Order 13993, BOP data",
    ),
    # --- WHO ---
    (
        "I will rejoin the World Health Organization on day one",
        "Campaign promise, 2020",
        "foreign_policy",
        "2020-07-07",
        True,
        "Signed letter on January 20, 2021 (day one) halting US withdrawal from WHO. US formally rejoined and resumed funding.",
        "WHO records, State Department",
    ),
    # --- MIDDLE EAST ---
    (
        "I support a two-state solution for Israel and Palestine",
        "Multiple statements, 2021-2023",
        "foreign_policy",
        "2021-05-20",
        False,
        "Two-state solution made no progress. October 7, 2023 Hamas attack triggered Israel-Gaza war. Over 30,000 Palestinian deaths by early 2024. Violence escalated dramatically. Peace talks nonexistent.",
        "State Department, UN records",
    ),
    # --- PERSONAL CONDUCT ---
    (
        "I will unite the country and restore the soul of America",
        "Campaign theme and inaugural address, 2021",
        "governance",
        "2021-01-20",
        False,
        "Polarization remained extremely high. Republicans largely opposed agenda. Bipartisan bills (infrastructure, CHIPS, gun safety) were exceptions. Midterms (2022) showed continued divisions. Country remains deeply divided.",
        "Polls, partisan voting patterns",
    ),
    # --- TRANSPARENCY ---
    (
        "I will restore transparency and trust in government",
        "Campaign promise, 2020",
        "transparency",
        "2020-06-30",
        True,
        "Released White House visitor logs (reversed Trump policy). Held regular press briefings. Released tax returns. Faced criticism over classified documents found at home/office but cooperated with DOJ investigation.",
        "White House records, media reports",
    ),
    # --- IMMIGRATION CONTINUED ---
    (
        "I will create a pathway to citizenship for 11 million undocumented immigrants",
        "Campaign promise, 2020",
        "immigration",
        "2020-11-07",
        False,
        "US Citizenship Act failed. No pathway to citizenship legislation passed. DACA restored but broader reform stalled. Executive actions limited by courts.",
        "Congressional record",
    ),
    # --- SUPREME COURT REFORM ---
    (
        "I will establish a commission to study Supreme Court reform",
        "Campaign statement, 2020",
        "governance",
        "2020-10-22",
        True,
        "Presidential Commission on the Supreme Court formed April 2021, issued report December 2021. Studied term limits, expansion, ethics reform. Did not recommend specific changes. No legislation followed.",
        "White House Commission report",
    ),
    # --- RAIL STRIKE ---
    (
        "I am a pro-union president, the most pro-union president in history",
        "Multiple statements, 2021-2023",
        "economy",
        "2021-09-08",
        False,
        "Supported PRO Act (failed in Senate). Became first president to walk a picket line (UAW, Sept 2023). However, signed legislation blocking rail strike (Dec 2022), forcing workers to accept contract without sick leave they wanted.",
        "Congressional record, media coverage",
    ),
    # --- ETHICS ---
    (
        "I will run the most ethical administration in American history",
        "Campaign promise, 2020",
        "transparency",
        "2020-07-04",
        False,
        "Hunter Biden investigations created ethics concerns despite no evidence of Joe Biden wrongdoing. Classified documents found at home/office. Special counsel appointed (both Biden docs and Trump docs). Standards higher than Trump but 'most ethical' is subjective claim.",
        "Special counsel reports, media investigations",
    ),
    # --- ECONOMY / MANUFACTURING ---
    (
        "We will bring manufacturing jobs back to America",
        "Campaign promise, State of the Union 2023",
        "economy",
        "2020-11-16",
        True,
        "Manufacturing added 800K jobs 2021-2023. CHIPS Act, IRA, infrastructure law spurred factory construction boom. Over $200B in announced semiconductor investments. Construction spending on manufacturing facilities hit record highs.",
        "BLS data, Commerce Department",
    ),
    # --- SOCIAL SECURITY / MEDICARE ---
    (
        "I will protect Social Security and Medicare, no cuts",
        "Campaign promise, multiple State of the Union addresses",
        "economy",
        "2020-04-10",
        True,
        "Did not propose cuts to Social Security or Medicare. Opposed Republican proposals to sunset programs. Inflation Reduction Act reduced Medicare drug costs. Benefits protected.",
        "OMB budget proposals, legislative record",
    ),
]

print("=" * 70)
print("SAY/DO POC: Joe Biden Contradiction Index")
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
    ("I will protect Social Security and Medicare", "economy"),
    ("I will secure the border", "immigration"),
    ("I will ban assault weapons", "governance"),
    ("I will unite the country", "governance"),
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
