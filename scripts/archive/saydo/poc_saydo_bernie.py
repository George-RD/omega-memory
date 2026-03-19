#!/usr/bin/env python3
"""Say/Do POC: Bernie Sanders Predictive Consistency Index.

Populates the Say/Do engine with well-documented public statements and
their corresponding votes/actions, then generates the full profile.

All statements are sourced from public record (floor speeches, campaign
statements, congressional votes, PolitiFact, GovTrack). This is an
accountability tool for public figures using verifiable facts.
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
DB_PATH = Path(__file__).parent.parent / "data" / "poc_saydo_bernie.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

store = SQLiteStore(db_path=str(DB_PATH))
bridge._store_instance = store
eng_mod._engine_instance = None  # Reset singleton

engine = get_saydo_engine()

ENTITY = "Bernie Sanders"
ENTITY_TYPE = "politician"

# ──────────────────────────────────────────────────────────────────────
# STATEMENTS + OUTCOMES
# Each tuple: (statement, source, category, date, followed_through, outcome_detail, evidence)
# ──────────────────────────────────────────────────────────────────────

DATA = [
    # --- MILITARY / FOREIGN POLICY ---
    (
        "I am opposed to giving the President a blank check to launch a unilateral invasion and occupation of Iraq",
        "House floor speech, October 2002",
        "military",
        "2002-10-09",
        True,
        "Voted NO on H.J.Res. 114, Authorization for Use of Military Force Against Iraq (Oct 10, 2002). One of 133 House members to vote against.",
        "Congressional Record, H.J.Res. 114 roll call",
    ),
    (
        "Opposed U.S. military intervention in the Persian Gulf, arguing for diplomacy over force",
        "House floor speech, January 1991",
        "military",
        "1991-01-10",
        True,
        "Voted NO on H.J.Res. 77, Authorization for Use of Military Force Against Iraq (Jan 12, 1991).",
        "Congressional Record, H.J.Res. 77 roll call",
    ),
    (
        "Anti-war, anti-interventionist stance on foreign military action",
        "Consistent public position throughout career",
        "military",
        "1999-03-01",
        False,
        "Voted YES on H.Con.Res. 42 authorizing NATO air operations against Yugoslavia (1999). When antiwar activists occupied his Burlington office to protest, he had them arrested. Adviser Jeremy Brecher resigned over the vote.",
        "VTDigger, Congressional Record",
    ),
    (
        "Brands himself as the anti-war candidate who opposes endless wars",
        "Campaign speeches, multiple occasions 2015-2020",
        "military",
        "2001-09-14",
        False,
        "Voted YES on S.J.Res. 23, the 2001 AUMF (Sept 14, 2001), which became the legal basis for two decades of military operations in Afghanistan and beyond. Only Rep. Barbara Lee voted no. Sanders did not push to repeal the AUMF for years.",
        "Congressional Record, S.J.Res. 23 roll call",
    ),
    (
        "We do not need to spend almost a trillion dollars on the military. The military-industrial complex must be reined in.",
        "Senate floor speeches, budget debates, multiple occasions",
        "military",
        "2015-11-01",
        False,
        "Actively lobbied to station F-35 fighter jets (part of a $1.7 trillion program, the most expensive weapons system in history) at Burlington International Airport in Vermont. Worked with Sen. Leahy to get Vermont to the top of the basing list.",
        "CNBC, VTDigger reporting on F-35 lobbying",
    ),
    (
        "U.S. support for Saudi Arabia's war in Yemen is unconstitutional. Congress must reclaim war powers authority.",
        "Senate floor speeches, press conferences, 2018-2022",
        "military",
        "2018-02-01",
        True,
        "Introduced S.J.Res. 54 (2018) invoking the War Powers Act to end U.S. support for the Saudi-led coalition in Yemen. Resolution passed the Senate 56-41 in December 2018. Built bipartisan coalition with Sen. Mike Lee (R-UT). Reintroduced in 2019 and 2022.",
        "NPR, Congressional Record, S.J.Res. 54 roll call",
    ),
    (
        "I voted against every defense budget under Trump",
        "Democratic debate, December 2019",
        "military",
        "2019-12-19",
        False,
        "PolitiFact rated this FALSE. Sanders was absent for one of the Trump-era defense budget votes. Also, Rep. Tulsi Gabbard (also a candidate) had voted against all of them, contradicting his claim of being the only one.",
        "PolitiFact fact-check, Congressional Record",
    ),

    # --- HEALTHCARE ---
    (
        "Healthcare is a human right, not a privilege. We need single-payer Medicare for All.",
        "Campaign speeches, Senate floor, multiple occasions 1970s-present",
        "healthcare",
        "2017-09-13",
        True,
        "Introduced the Medicare for All Act of 2017 (S.1804), 2019 (S.1129), and 2025 (S.1506). Built co-sponsor coalitions each time (16 Senate co-sponsors in 2017). None passed, but consistently authored and reintroduced the legislation.",
        "Congressional Record, bill text",
    ),
    (
        "Advocated for single-payer healthcare during the ACA debate, introduced single-payer amendment",
        "Senate floor, 2009-2010",
        "healthcare",
        "2009-12-01",
        True,
        "Withdrew single-payer amendment under pressure, then voted YES on the ACA (H.R. 3590, Dec 24, 2009). Said: 'The bill is not as strong as I wanted... but it begins to move this country toward comprehensive affordable health care.' Secured $11B for community health centers as condition for his vote.",
        "PolitiFact, Congressional Record",
    ),

    # --- ECONOMIC / WALL STREET ---
    (
        "Wall Street should not be bailed out by taxpayers",
        "Senate floor speech opposing TARP, 2008",
        "economy",
        "2008-10-01",
        True,
        "Voted NO on the Emergency Economic Stabilization Act of 2008 (TARP, $700B Wall Street bailout). Also voted to block the second tranche of TARP funds in January 2009 (S.J.Res. 5). Most Democrats including Clinton and Obama voted for the bailout.",
        "FactCheck.org, Congressional Record",
    ),
    (
        "NAFTA, CAFTA, and PNTR with China are disastrous for American workers. I am proud to have voted against all of them.",
        "Campaign speeches, Senate floor, multiple occasions 1993-2016",
        "economy",
        "1993-11-17",
        True,
        "Voted NO on NAFTA (1993), NO on PNTR with China (2000), NO on CAFTA (2005). Introduced legislation to reverse PNTR with China (71 co-sponsors). Opposed TPP. One of the most consistent trade positions across his career.",
        "OnTheIssues, Congressional Record",
    ),
    (
        "We need to break up too-big-to-fail banks and reinstate Glass-Steagall",
        "Senate floor speeches, campaign platform, 2010-2020",
        "economy",
        "2010-07-21",
        True,
        "Voted YES on Dodd-Frank Wall Street Reform Act (2010). Voted NO on the 2018 Economic Growth, Regulatory Relief, and Consumer Protection Act (which rolled back parts of Dodd-Frank). Introduced legislation to break up large banks and reinstate Glass-Steagall.",
        "Congressional Record",
    ),
    (
        "We need a $15 federal minimum wage. Fight for $15.",
        "Campaign platform, Senate floor, 2015-present",
        "economy",
        "2015-07-22",
        True,
        "Introduced the Raise the Wage Act (multiple iterations). Introduced the 'Stop BEZOS Act' (2018) targeting Amazon's low wages. Amazon subsequently raised its minimum wage to $15/hour. Analysts credited Sanders' public pressure campaign.",
        "Washington Post, Congressional Record",
    ),

    # --- CRIMINAL JUSTICE ---
    (
        "All the jails in the world will not solve crime caused by poverty, lack of education, and hopelessness",
        "House floor speech criticizing punitive provisions of the 1994 Crime Bill, April 1994",
        "criminal_justice",
        "1994-04-13",
        False,
        "Voted YES on the Violent Crime Control and Law Enforcement Act of 1994 (H.R. 3355), which contributed to mass incarceration through 'three strikes' provisions, mandatory minimums, and prison building incentives. Justified vote by pointing to Violence Against Women Act and assault weapons ban provisions. Later said: 'I'm not happy I voted for a terrible bill.'",
        "CNN KFile, NBC News, Congressional Record",
    ),

    # --- IMMIGRATION ---
    (
        "Open borders is a Koch brothers proposal. What this immigration legislation is really about is bringing millions of low-wage temporary workers to drive down wages.",
        "Vox interview (2015), House floor speech (2007)",
        "immigration",
        "2007-06-01",
        True,
        "Voted NO on the 2007 Comprehensive Immigration Reform Act (S.1348), effectively helping kill the bill alongside Republican opponents. His reasoning aligned with AFL-CIO labor concerns about guest worker provisions.",
        "Washington Post, TIME, Congressional Record",
    ),
    (
        "Shifted to championing expansive immigration policies: decriminalizing border crossings, moratorium on deportations",
        "2020 presidential campaign platform",
        "immigration",
        "2019-11-07",
        False,
        "Voted YES on the 2013 Border Security, Economic Opportunity, and Immigration Modernization Act (S.744), which also included guest worker programs he had previously opposed. By 2020, his immigration platform was dramatically more liberal than his 2007 votes. A genuine position evolution/reversal.",
        "Senate vote record, campaign platform documents",
    ),

    # --- CLIMATE / ENERGY ---
    (
        "Climate change is the single greatest threat facing our planet. I was the first national politician to publicly oppose Keystone XL.",
        "Senate floor, campaign speeches, 2011-present",
        "climate",
        "2011-08-01",
        True,
        "Voted NO on Keystone XL Pipeline approval (S.1, 2015). Voted NO on lifting crude oil export ban. Voted NO on expediting LNG exports. Introduced Keep It in the Ground Act (2015). Lifetime League of Conservation Voters score: 95%. Perfect 100% in 2015.",
        "LCV scorecard, Congressional Record",
    ),
    (
        "The Inflation Reduction Act contains massive giveaways to the fossil fuel industry, requiring 60 million acres of public waters be offered to oil and gas each year",
        "Senate floor criticism of IRA, August 2022",
        "climate",
        "2022-08-07",
        True,
        "Voted YES on the Inflation Reduction Act (Aug 7, 2022) despite public criticism. Proposed multiple amendments to expand the bill (all rejected). Said the 'pluses' outweighed the 'minuses.' Transparent about the compromise.",
        "Sanders Senate press release, Congressional Record",
    ),

    # --- GUNS ---
    (
        "Represented rural Vermont's gun culture and opposed federal overreach on firearms",
        "Campaign positions, 1990-1993",
        "guns",
        "1991-02-01",
        True,
        "Voted NO on the Brady Handgun Violence Prevention Act five times between 1991-1993, including the final passage vote. Won 1990 House race partly with NRA support. Justified as representing rural Vermont gun owners.",
        "PolitiFact, Congressional Record",
    ),
    (
        "Argued he was protecting small Vermont gun shops from frivolous lawsuits",
        "Senate floor, 2003-2005",
        "guns",
        "2005-07-01",
        False,
        "Voted YES on the Protection of Lawful Commerce in Arms Act (PLCAA) in 2003 and 2005, shielding gun manufacturers from civil lawsuits. Then in 2016, under pressure from Hillary Clinton, co-sponsored legislation to REPEAL the PLCAA. A clean flip-flop.",
        "PolitiFact, Congressional Record",
    ),
    (
        "The world has changed, and my views have changed. I now support expanded background checks and gun control.",
        "2020 campaign, multiple debates",
        "guns",
        "2020-01-14",
        True,
        "By 2020, fully supported expanded background checks, assault weapons ban, and gun manufacturer liability. Voted for gun control measures in the Senate. NRA rating dropped from C- to F over career. Acknowledged the evolution honestly.",
        "Campaign platform, NRA scorecard, Congressional Record",
    ),

    # --- RUSSIA SANCTIONS ---
    (
        "Russian interference in elections is an outrage. Russia must be held accountable.",
        "Senate statements, press conferences, 2016-2017",
        "foreign_policy",
        "2017-07-01",
        False,
        "Voted NO on the Magnitsky Act (2012). Voted NO on the 2017 Countering America's Adversaries Through Sanctions Act (one of only 2 senators to vote no, alongside Rand Paul). Explained opposition was about protecting the Iran deal (JCPOA), but optics contradicted his 'hold Russia accountable' rhetoric.",
        "PolitiFact, Congressional Record",
    ),

    # ──────────────────────────────────────────────────────────────────────
    # EXPANDED DATASET (38 additional data points)
    # ──────────────────────────────────────────────────────────────────────

    # --- CRIMINAL JUSTICE (expanded) ---
    (
        "We must end cash bail, end private prisons, end mandatory minimums, reinstate the federal parole system",
        "Senate floor vote and Twitter statement, December 2018",
        "criminal_justice",
        "2018-12-18",
        True,
        "Voted Yea on S.756, the First Step Act, which passed 87-12. Bill retroactively applied Fair Sentencing Act, reduced mandatory minimums, expanded early-release programs. Continued advocating for broader reforms.",
        "GovTrack Senate Vote #271, 115th Congress",
    ),
    (
        "When I am president, we will abolish the death penalty",
        "Senate floor speech on criminal justice reform, July 2019",
        "criminal_justice",
        "2019-07-01",
        False,
        "Not elected president. However, in 1991 voted against expanding federal death penalty (H.R.3371). Voted for amendment to 1994 Crime Bill to replace all federal death sentences with life in prison (failed). Then voted for the larger crime bill containing death penalty expansions anyway.",
        "Sanders Senate press release, OnTheIssues",
    ),
    (
        "Marijuana should be removed from the Controlled Substances Act entirely",
        "Senate bill introduction (S.2237), November 2015",
        "criminal_justice",
        "2015-11-04",
        True,
        "Introduced the Ending Federal Marijuana Prohibition Act of 2015 (S.2237), the first-ever Senate bill to end federal marijuana prohibition. Zero co-sponsors, never advanced. Later co-sponsored Booker's Marijuana Justice Act (2017). Continued advocating federal legalization.",
        "Congress.gov S.2237",
    ),

    # --- FOREIGN POLICY (expanded) ---
    (
        "The test of a great nation is not how many wars it can engage in, but how it can resolve conflicts peacefully. I support the Iran nuclear deal.",
        "Senate floor vote and press release, September 2015",
        "foreign_policy",
        "2015-09-10",
        True,
        "Voted against the resolution of disapproval (effectively supporting the JCPOA). Cloture vote on resolution failed 58-42, allowing deal to proceed. Consistently defended the deal through 2018 when Trump withdrew.",
        "Sanders Senate press release, Arms Control Association",
    ),
    (
        "Introduced resolutions to block approximately $20 billion in U.S. arms sales to Israel, citing violations of international law in Gaza",
        "Senate resolutions S.J.Res.73-75, November 2024",
        "foreign_policy",
        "2024-11-01",
        True,
        "All three resolutions failed (79-18, 79-18, 81-16). However, 19 senators voted for one or more resolutions, unprecedented for Israel arms sale disapproval votes. By 2025, a majority of Senate Democrats voted with Sanders on subsequent resolutions.",
        "Sanders Senate press release, Newsweek roll call",
    ),
    (
        "We must learn the lessons of the past and not be in the business of regime change. Maduro is a vicious tyrant but military intervention is wrong.",
        "Senate statement and press releases, January-February 2019",
        "foreign_policy",
        "2019-01-24",
        True,
        "Voted with full Senate Democratic Caucus to advance bipartisan War Powers resolution blocking military action against Venezuela. Opposed broad economic sanctions. Maintained consistent position opposing both Maduro and U.S. interventionism.",
        "Sanders Senate statement, CBS News",
    ),
    (
        "When Fidel Castro came into office, he had a massive literacy program. Is that a bad thing?",
        "CBS 60 Minutes interview, February 23, 2020",
        "foreign_policy",
        "2020-02-23",
        True,
        "Doubled down when challenged, saying 'The truth is the truth.' Had made similar comments since the 1980s. Consistent with his worldview but widely seen as politically damaging. Contributed to losses in Florida during 2020 primary. Did condemn Castro's imprisonment of dissidents when pressed.",
        "CNN, NPR fact-check",
    ),
    (
        "Cast sole Democratic vote against standalone $14.3 billion aid package to Israel",
        "Senate vote, November 2023",
        "foreign_policy",
        "2023-11-01",
        True,
        "Only member of the Democratic caucus to vote against the bill, which failed 51-49 (needed 60 for cloture). While bill failed for procedural reasons (Republicans wanted IRS cuts to offset), Sanders' opposition was on substance. Most isolated Democratic voice on this vote.",
        "Sanders Senate press release",
    ),

    # --- LABOR / UNION ---
    (
        "Workers must have the right to join a union through card-check without employer interference",
        "Congressional legislation, Workplace Democracy Act, 1992-2018",
        "labor",
        "2007-06-26",
        True,
        "Introduced the Workplace Democracy Act in 1992, re-introduced nearly every two years. The 2007 Employee Free Choice Act passed the House but was filibustered in Senate (51-48 on cloture). Sanders voted Yea. Continued reintroducing updated versions through 2018.",
        "Congressional Record, Wikipedia: Workplace Democracy Act",
    ),
    (
        "The PRO Act is the most significant piece of labor legislation proposed in modern history",
        "Senate legislation and press statements, 2021-2023",
        "labor",
        "2021-02-04",
        True,
        "PRO Act passed House 225-206 in March 2021. As HELP Committee chair, advanced it through committee on party-line vote. Never received full Senate floor vote due to filibuster. Reintroduced in 2023.",
        "Sanders Senate press release, Common Dreams",
    ),
    (
        "No company is above the law. Starbucks must end its illegal union busting.",
        "HELP Committee hearing, March 29, 2023",
        "labor",
        "2023-03-29",
        True,
        "As HELP Committee chairman, convened hearing threatening to subpoena former CEO Howard Schultz. Schultz initially refused, agreed under threat of subpoena. NLRB had filed over 80 complaints against Starbucks with 500+ unfair labor practice charges. Hearing elevated national attention to Starbucks Workers United organizing.",
        "NPR, Sanders prepared remarks",
    ),
    (
        "You're sending a message not just to Kellogg's, but to every corporate CEO in this country",
        "Rally speech at Kellogg's picket line, December 17, 2021",
        "labor",
        "2021-12-17",
        True,
        "Joined striking Kellogg's workers on picket line in Battle Creek, Michigan. 1,400-worker strike lasted 11 weeks. Workers ratified new 5-year contract with $1.10/hour wage increase, pension boost, and moratorium on plant closures.",
        "NPR, WWMT local reporting",
    ),
    (
        "Railroad workers who get sick get a mark for missing work and in some cases will be fired. They deserve paid sick leave.",
        "Senate floor speech and amendment, December 1, 2022",
        "labor",
        "2022-12-01",
        True,
        "Introduced amendment to add 7 days paid sick leave to imposed railroad labor agreement. Amendment failed 52-43 (every Democrat except Manchin voted Yea, plus 6 Republicans). Then voted against final bill imposing contract without sick leave. Contract imposed 80-15, averting strike but without sick leave.",
        "VTDigger, NPR",
    ),
    (
        "Attended Walmart shareholder meeting to demand $15/hour wages and employee board representation",
        "Shareholder meeting speech, June 5, 2019",
        "labor",
        "2019-06-05",
        True,
        "Presented shareholder resolution to put hourly workers on the board. Walmart's chief legal officer dismissed it. Walmart did not raise to $15 at that time (starting wage $11). Walmart eventually raised to $12/hour (2021) then $14/hour (2023), still below Sanders' demand.",
        "NPR, Common Dreams",
    ),

    # --- EDUCATION ---
    (
        "We will eliminate undergraduate tuition at public colleges, funded by a tax on Wall Street speculation",
        "College for All Act (S.1373), May 2015",
        "education",
        "2015-05-19",
        True,
        "Introduced College for All Act in four consecutive congressional sessions (2015, 2019, 2021, 2023). None advanced past committee. 2023 version would also cancel all student loan debt. Persistent legislative action, never enacted.",
        "Congress.gov S.1373, S.1288, S.1963",
    ),

    # --- TECHNOLOGY / PRIVACY ---
    (
        "The Patriot Act gives the government far too much power to spy on innocent United States citizens",
        "Congressional votes and press statements, 2001-2015",
        "technology",
        "2001-10-24",
        True,
        "Voted Nay on the original USA PATRIOT Act (H.R.3162, October 2001) and every subsequent reauthorization (2006, 2011, 2015). In 2005, passed amendment 238-187 to limit Section 215 library searches. Consistently opposed across 14+ years.",
        "Sanders Senate press release, TIME",
    ),
    (
        "The USA FREEDOM Act does not go far enough to protect civil liberties. It still allows collection of data on Americans who have nothing to do with terrorism.",
        "Senate vote, June 2, 2015",
        "technology",
        "2015-06-02",
        True,
        "Voted Nay on USA FREEDOM Act (H.R.2048) which passed 67-32. While most civil liberties groups supported the bill as incremental improvement, Sanders argued it was insufficient. Aligned with some libertarian Republicans (Rand Paul) who also voted Nay.",
        "Senate Roll Call Vote #201, 114th Congress",
    ),
    (
        "I am not convinced Mr. Brennan is adequately sensitive to civil liberties as part of ensuring national security",
        "Senate confirmation vote and statement, March 2013",
        "technology",
        "2013-03-07",
        True,
        "Voted against confirming John Brennan as CIA Director. Brennan confirmed 63-34. Sanders was one of three Democrats/Independents to vote Nay (with Leahy and Merkley). Cited drone program concerns and civil liberties.",
        "Sanders Senate statement, Washington Post",
    ),
    (
        "We would absolutely break up Facebook, Google, and Amazon",
        "Washington Post event (2019), HELP Committee actions (2023)",
        "technology",
        "2019-06-01",
        True,
        "As HELP chair, subpoenaed Amazon for safety records and convened hearings. Launched investigation into Amazon warehouse safety. No antitrust legislation bearing his name introduced. Role was primarily oversight and public pressure rather than direct legislative action on breakups.",
        "PBS, CNBC",
    ),

    # --- GOVERNANCE ---
    (
        "If Republicans can end the filibuster to install right-wing judges, Democrats can and must end the filibuster to codify Roe v. Wade",
        "Senate floor speech, June 2022",
        "governance",
        "2022-06-24",
        True,
        "Position evolved from favoring only 'talking filibuster' (2019) to supporting full elimination for specific issues (voting rights, abortion). Voted for filibuster carve-outs for voting rights (January 2022) and abortion access. Senate never mustered 50 votes due to Manchin and Sinema.",
        "Sanders Senate press release, PBS",
    ),
    (
        "Corporations are not people and money is not speech. We must overturn Citizens United.",
        "S.J.Res.33, Saving American Democracy Amendment, December 2011",
        "governance",
        "2011-12-08",
        True,
        "Introduced constitutional amendment to overturn Citizens United. Never received a vote (requires 2/3 of both chambers). Continued sponsoring updated versions and co-sponsored DISCLOSE Act. Ran both presidential campaigns without Super PAC, though allied group Our Revolution operated as dark money on his behalf.",
        "Congress.gov S.J.Res.33",
    ),
    (
        "We need a full GAO audit of the Federal Reserve's emergency lending during the financial crisis",
        "Senate amendment to Dodd-Frank, May 2010",
        "governance",
        "2010-05-06",
        True,
        "Amendment passed the Senate 96-0 and was included in final Dodd-Frank Act. GAO audit revealed $16 trillion in secret emergency loans to U.S. and foreign banks. Later supported Rand Paul's broader 'Audit the Fed' bill (2016) which was filibustered 53-44.",
        "Sanders press release, Common Dreams",
    ),
    (
        "Dark money is a cancer on our democracy. We must require disclosure of all large campaign donations.",
        "DISCLOSE Act co-sponsorship, multiple sessions 2010-2018",
        "governance",
        "2010-07-27",
        True,
        "Co-sponsored DISCLOSE Act requiring organizations spending $10K+ on elections to file public FEC disclosures. Passed House in 2010 but filibustered in Senate (59-39, one vote short). Sanders voted Yea on every attempt. Reintroduced in subsequent sessions, consistently failed.",
        "Wikipedia: DISCLOSE Act, Sanders press release",
    ),

    # --- ECONOMY (expanded) ---
    (
        "This tax bill will be remembered as one of the greatest robberies in American history",
        "Senate floor speech opposing Trump tax cuts, December 2017",
        "economy",
        "2017-12-01",
        True,
        "Voted Nay on Tax Cuts and Jobs Act. Bill passed 51-48 on party lines. His prediction partially materialized: Republicans later cited deficit to push spending cuts. CBO confirmed 62% of individual tax benefits go to top 1% by 2027. Introduced legislation in 2023 to raise corporate rate back to 35%.",
        "RealClearPolitics, Sanders vote statement",
    ),
    (
        "The American Rescue Plan is the most significant piece of legislation to benefit working families in modern history",
        "Senate Budget Committee and floor vote, March 2021",
        "economy",
        "2021-03-06",
        True,
        "As Senate Budget Committee Chairman, shepherded $1.9T American Rescue Plan through reconciliation. Passed 50-49. Included $1,400 payments, Child Tax Credit expansion (temporarily cut child poverty in half). His $15 minimum wage amendment failed 58-42 (8 Democrats voted Nay).",
        "Sanders statement on ARP, Senate Budget Committee",
    ),
    (
        "Introduced amendment to raise federal minimum wage to $15/hour as part of the American Rescue Plan",
        "Vote-a-rama amendment, March 5, 2021",
        "economy",
        "2021-03-05",
        True,
        "Amendment failed 58-42. Seven Democrats (Sinema, Coons, Carper, Hassan, Shaheen, Tester, Manchin) and Independent King voted Nay alongside all Republicans. Sanders declared he would not give up. Federal minimum wage remains $7.25 as of 2026.",
        "Newsweek, The Week",
    ),
    (
        "Voted for the American Recovery and Reinvestment Act to combat the Great Recession",
        "Senate vote, February 13, 2009",
        "economy",
        "2009-02-13",
        True,
        "Voted Yea on ARRA ($787B stimulus). Passed 60-38 with Sanders joining Democrats and three Republicans. Later argued the stimulus was too small.",
        "GovTrack Senate Vote #64, 111th Congress",
    ),
    (
        "We must expand Social Security benefits and extend solvency by lifting the payroll tax cap on income above $250,000",
        "S.393, Social Security Expansion Act, February 2023",
        "economy",
        "2023-02-13",
        True,
        "Introduced S.393 to increase benefits by $2,400/year and extend solvency through 2096. Co-sponsored by Warren and others. Referred to Finance Committee, never received vote. Reintroduced in 2025. Would not raise taxes on 93% of households.",
        "Congress.gov S.393",
    ),
    (
        "Delivered 8.5-hour filibuster speech against extending Bush-era tax cuts for the wealthy",
        "Senate floor speech, December 10, 2010",
        "economy",
        "2010-12-10",
        False,
        "Tax deal passed the Senate 81-19 despite marathon speech. Sanders voted Nay. Speech became a bestselling book ('The Speech') and elevated his national profile, laying groundwork for 2016 presidential campaign. Action failed to achieve stated goal.",
        "NPR, C-SPAN",
    ),
    (
        "Americans can import fish from all over the world but cannot bring medicine from Canada. We need drug importation.",
        "Vote-a-rama on S.Con.Res.3, January 11, 2017",
        "economy",
        "2017-01-11",
        True,
        "Co-sponsored S.Amdt.178 (Klobuchar amendment) to allow prescription drug importation from Canada. Amendment failed 52-46. 13 Democrats voted Nay (including Cory Booker). 12 Republicans voted Yea. Exposed intra-party divisions on pharma policy.",
        "Congress.gov S.Amdt.178, The Intercept",
    ),

    # --- HEALTHCARE (expanded) ---
    (
        "As Veterans Affairs Committee Chairman, co-authored bipartisan $17 billion VA reform bill with John McCain",
        "Senate legislation and press conference, June-August 2014",
        "healthcare",
        "2014-06-09",
        True,
        "S.2450 provisions incorporated into H.R.3230, passed Senate and signed as P.L. 113-146 on August 7, 2014 (only 3 Nay votes). Allowed veterans to see private doctors when facing long wait times. Critics noted VA scandal occurred under Sanders' chairmanship and he was slow to recognize its severity.",
        "Congress.gov S.2450, Senate Veterans Affairs Committee",
    ),

    # --- MILITARY (expanded) ---
    (
        "The Pentagon doesn't need $886 billion. We should cut defense spending by 10%.",
        "Annual Senate NDAA votes, 2021-2024",
        "military",
        "2023-12-13",
        True,
        "Consistently voted Nay on NDAA in multiple years (FY2022 $770B, FY2024 $886B, FY2025 ~$895B). Amendment to cut Pentagon budget 10% failed 88-11. One of only 11-13 senators regularly opposing the annual defense bill.",
        "Truthout, The Hill",
    ),
    (
        "I wouldn't end the drone program. Drones should be used very, very selectively and effectively.",
        "The Hill interview, August 2015; NBC Meet the Press",
        "military",
        "2015-08-01",
        True,
        "Disappointed anti-war supporters who expected full opposition to drone strikes. Acknowledged 'there are times and places where drone attacks have been effective' while also saying 'when you kill innocent people, people become anti-American.' Nuanced position consistent but at odds with broader anti-interventionist rhetoric.",
        "The Hill, NBC News",
    ),
]

print("=" * 70)
print("SAY/DO POC: Bernie Sanders Predictive Consistency Index")
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
    ("I will push for Medicare for All until it passes", "healthcare"),
    ("I will vote against the next defense spending increase", "military"),
    ("I will oppose any trade deal that hurts American workers", "economy"),
    ("I will fight to break up big tech monopolies", "technology"),
    ("I will stand with striking workers on the picket line", "labor"),
    ("I will block arms sales to countries violating human rights", "foreign_policy"),
    ("I will introduce legislation to reform the criminal justice system", "criminal_justice"),
    ("I will vote against extending warrantless surveillance", "technology"),
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
