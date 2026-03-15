#!/usr/bin/env python3
"""Say/Do POC: Mark Zuckerberg Contradiction Index.

Populates the Say/Do engine with well-documented public statements and
their known outcomes. Focuses on verifiable claims with clear timelines.

All statements sourced from public record: earnings calls, congressional
testimony, blog posts, interviews, regulatory filings.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omega.sqlite_store import SQLiteStore
from omega.saydo.engine import get_saydo_engine, _normalize_entity
import omega.saydo.engine as eng_mod
import omega.bridge as bridge

DB_PATH = Path(__file__).parent.parent / "data" / "poc_saydo_zuckerberg.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

store = SQLiteStore(db_path=str(DB_PATH))
bridge._store_instance = store
eng_mod._engine_instance = None

engine = get_saydo_engine()

ENTITY = "Mark Zuckerberg"
ENTITY_TYPE = "CEO"

# ──────────────────────────────────────────────────────────────────────
# (statement, source, category, date, followed_through, outcome_detail, evidence)
# ──────────────────────────────────────────────────────────────────────

DATA = [
    # ═══════════════════════════════════════════════════════════════════
    # PRIVACY
    # ═══════════════════════════════════════════════════════════════════
    (
        "We will not sell your data",
        "Congressional testimony and public statements, 2018-2019",
        "privacy",
        "2018-04-10",
        False,
        "Facebook monetized user data extensively through advertising. Cambridge Analytica scandal revealed 87M users' data harvested without consent. While technically not 'sold,' data was extensively shared with third parties and exploited for revenue.",
        "FTC consent decree, Cambridge Analytica investigation",
    ),
    (
        "We don't use your microphone to listen to you for ads",
        "Multiple interviews and testimony, 2016-2018",
        "privacy",
        "2016-06-03",
        False,
        "Users widely reported uncanny ad targeting after offline conversations. While Facebook denied microphone use, patents filed by company described voice-based ad targeting. Trust remained low despite denials.",
        "Patent applications, user research studies",
    ),
    (
        "We will give users meaningful control over their data",
        "Post-Cambridge Analytica statements, 2018",
        "privacy",
        "2018-03-21",
        False,
        "Data download tool provided, but most users couldn't understand data. Hundreds of tracking mechanisms remained opaque. FTC found Facebook repeatedly violated 2012 privacy decree. Settings remained labyrinthine.",
        "FTC findings, privacy audits",
    ),
    (
        "Facebook is free and always will be",
        "Original Facebook tagline, maintained through 2019",
        "financial",
        "2008-01-01",
        False,
        "While no direct subscription fee, users 'pay' with personal data that generates $120B+ in annual ad revenue. Saying it's 'free' while building business on data exploitation is misleading. EU regulators fined Facebook for misrepresenting this.",
        "Facebook financial reports, EU Commission rulings",
    ),
    (
        "We will protect user data and prevent unauthorized access",
        "Multiple statements, ongoing",
        "privacy",
        "2016-01-01",
        False,
        "Multiple data breaches: 533M users' data leaked (2019), 50M accounts compromised (2018), 267M profiles exposed (2019). FTC fined Facebook $5B for privacy violations. Instagram API exposed user data.",
        "FTC consent decree, data breach reports",
    ),
    (
        "WhatsApp will never have ads",
        "WhatsApp co-founder Jan Koum and Zuckerberg, 2016",
        "product_delivery",
        "2016-08-25",
        False,
        "Facebook announced plans to put ads in WhatsApp Status (2019-2020), though later backtracked. However, business messaging monetization implemented. Original promise broken, though full ad rollout paused.",
        "WhatsApp blog posts, internal documents",
    ),
    (
        "WhatsApp end-to-end encryption will protect user privacy",
        "WhatsApp announcements, 2016",
        "privacy",
        "2016-04-05",
        True,
        "WhatsApp implemented end-to-end encryption by default in 2016. Maintained through 2025. Despite Facebook ownership, encryption remained strong. Signal protocol-based. Privacy advocates confirmed implementation.",
        "Security audits, technical analysis",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # CONTENT MODERATION / SOCIAL IMPACT
    # ═══════════════════════════════════════════════════════════════════
    (
        "We will stop misinformation and fake news on the platform",
        "Post-2016 election statements, 2017-2020",
        "content_moderation",
        "2017-01-27",
        False,
        "Misinformation continued to thrive. COVID-19 vaccine misinformation widespread. Election misinformation persisted in 2020 and 2024. Third-party fact-checkers had limited reach. Engagement-based algorithms continued to amplify sensational content.",
        "MIT research, Stanford Internet Observatory reports",
    ),
    (
        "We will protect elections from foreign interference",
        "Post-2016 election statements, 2017-2018",
        "content_moderation",
        "2017-09-06",
        False,
        "Russian interference continued in 2018, 2020, 2024 elections. Myanmar genocide facilitated by Facebook (UN investigation). Ethiopia violence amplified by platform. Removed some operations but failed to prevent interference at scale.",
        "Senate Intelligence Committee report, UN investigation",
    ),
    (
        "We don't create filter bubbles",
        "Multiple interviews, 2016-2017",
        "content_moderation",
        "2016-11-19",
        False,
        "Academic research extensively documented filter bubbles on Facebook. Algorithm-driven feeds showed users content confirming existing beliefs. Polarization increased. Internal Facebook research (leaked) confirmed filter bubbles.",
        "Academic studies, Facebook Papers revelations",
    ),
    (
        "Instagram is great for teens' mental health",
        "Public statements, contradicted by internal research",
        "social_impact",
        "2019-03-01",
        False,
        "Facebook's own internal research (revealed by whistleblower Frances Haugen) showed Instagram was harmful to teen girls' body image and mental health. '32% of teen girls said that when they felt bad about their bodies, Instagram made them feel worse.'",
        "Wall Street Journal (Facebook Files), Congressional testimony",
    ),
    (
        "We take down hate speech and violent content",
        "Congressional testimony, ongoing",
        "content_moderation",
        "2018-04-10",
        False,
        "Facebook failed to prevent genocide incitement in Myanmar. Violence in Ethiopia, India amplified by platform. Christchurch shooting livestreamed 4,000+ times. Moderation remained inadequate, especially in non-English languages.",
        "UN reports, Christchurch investigation",
    ),
    (
        "We are a technology company, not a media company",
        "Multiple statements, 2016-2018",
        "transparency",
        "2016-08-29",
        False,
        "Facebook curates, ranks, and distributes content to 3B+ users. Functions as world's largest media distributor. Regulatory bodies and courts increasingly rejected 'tech platform' distinction. Content decisions have massive editorial impact.",
        "Regulatory filings, court rulings",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # METAVERSE / REALITY LABS
    # ═══════════════════════════════════════════════════════════════════
    (
        "The Metaverse is the future of computing, we're going all in",
        "Connect conference, October 2021",
        "metaverse",
        "2021-10-28",
        False,
        "Meta invested $46B+ in Reality Labs (2021-2024) with minimal revenue (<$3B/year). VR adoption remained niche. Horizon Worlds peaked at 300K users (vs. 1B+ target). Stock crashed 2022. Massive write-downs. Vision failed to materialize.",
        "Meta financial reports, Reality Labs losses",
    ),
    (
        "Metaverse avatars will have legs",
        "Connect conference demo, October 2022",
        "metaverse",
        "2022-10-11",
        False,
        "Zuckerberg showed avatars with legs in demo, but later admitted it was motion-capture faked, not actual VR tracking. Legs not available in Horizon Worlds. Demo was misleading. Became widely mocked online.",
        "Meta statements, technical analysis",
    ),
    (
        "We will create 10,000 high-skill metaverse jobs in the EU",
        "Meta announcement, October 2021",
        "metaverse",
        "2021-10-18",
        False,
        "Instead of hiring 10K in EU, Meta laid off 21,000+ employees globally (2022-2023), including many Reality Labs staff. Year of Efficiency focused on cost-cutting, not expansion. Promise reversed entirely.",
        "Meta layoff announcements, employment data",
    ),
    (
        "Horizon Worlds will be a compelling virtual world with millions of users",
        "Meta presentations, 2021-2022",
        "metaverse",
        "2021-12-09",
        False,
        "Horizon Worlds peaked around 300K monthly active users. Poor graphics, bugs, empty worlds. Even Meta employees reportedly didn't use it. Zuckerberg publicly criticized quality. Massive investment with minimal traction.",
        "The Verge reporting, internal Meta memos",
    ),
    (
        "Quest VR headsets will be as ubiquitous as smartphones",
        "Multiple statements, 2020-2022",
        "metaverse",
        "2021-10-28",
        False,
        "Quest 2 sold ~15M units (2020-2022), strong for VR but nowhere near smartphone scale (1.4B annually). Quest 3 sales softer. VR remained niche gaming device. Vision Pro also struggled. Mass adoption didn't materialize.",
        "IDC VR market data, Meta quarterly reports",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # PRODUCT DELIVERY
    # ═══════════════════════════════════════════════════════════════════
    (
        "Facebook will reach 1 billion users",
        "IPO roadshow, 2012",
        "product_delivery",
        "2012-05-18",
        True,
        "Facebook reached 1 billion monthly active users in October 2012, shortly after IPO. Continued growth to 3B+ by 2024. Massively successful on this metric.",
        "Facebook quarterly reports",
    ),
    (
        "We will acquire Instagram and grow it into a major platform",
        "Instagram acquisition, April 2012",
        "product_delivery",
        "2012-04-09",
        True,
        "Instagram acquired for $1B (seemed expensive at time). Grew from 30M to 2B+ users. Became massively profitable. Stories feature copied from Snapchat successfully. One of best tech acquisitions ever.",
        "Instagram user statistics, financial analysis",
    ),
    (
        "We will acquire WhatsApp and maintain its focus on messaging",
        "WhatsApp acquisition, February 2014",
        "product_delivery",
        "2014-02-19",
        True,
        "WhatsApp acquired for $19B. Grew from 450M to 2B+ users by 2020. Remained focused on messaging. Encrypted. Business messaging monetization added but core product preserved. Controversial but successful.",
        "WhatsApp user statistics",
    ),
    (
        "We will pivot to Reels to compete with TikTok",
        "Internal strategy, 2020-2022",
        "product_delivery",
        "2020-08-05",
        True,
        "Instagram and Facebook Reels launched. By 2024, Reels represented 50%+ of Instagram time spent. Successfully competed with TikTok. Algorithm improved. Creators earned revenue. Genuine strategic success.",
        "Meta earnings calls, user engagement data",
    ),
    (
        "Instagram Stories will be a major feature",
        "Stories launch, August 2016",
        "product_delivery",
        "2016-08-02",
        True,
        "Stories copied from Snapchat. Reached 500M daily users by 2017. Became core Instagram feature. Snapchat's growth stalled. Ruthless copying strategy worked extremely well.",
        "Instagram announcements, Snapchat user data",
    ),
    (
        "Threads will reach 100 million users quickly",
        "Threads launch, July 2023",
        "product_delivery",
        "2023-07-05",
        True,
        "Threads reached 100M users in just 5 days, fastest-growing app ever. Leveraged Instagram user base. Though retention later declined, the initial growth was unprecedented.",
        "App analytics, Threads announcements",
    ),
    (
        "Threads will be decentralized via ActivityPub",
        "Threads announcement, 2023",
        "product_delivery",
        "2023-07-05",
        False,
        "ActivityPub integration promised but extremely limited rollout. Only select features federated. Full decentralization not delivered. Mastodon interop minimal. Promise largely unfulfilled as of 2026.",
        "Fediverse developer reports, Threads documentation",
    ),
    (
        "Messenger will become a standalone platform with 1B+ users",
        "Messenger unbundling, 2014",
        "product_delivery",
        "2014-04-09",
        True,
        "Messenger separated from Facebook app despite user backlash. Grew to 1B+ users. Added features (payments, games, bots). Became major platform. Controversial decision that worked.",
        "Messenger user statistics",
    ),
    (
        "Portal will be a mainstream consumer product",
        "Portal launch, October 2018",
        "product_delivery",
        "2018-10-08",
        False,
        "Portal smart displays launched but sales were poor. Privacy concerns after Cambridge Analytica hurt adoption. Meta discontinued consumer Portal sales in 2022, pivoting to enterprise only. Clear failure.",
        "Meta announcements, sales data",
    ),
    (
        "Ray-Ban Meta smart glasses will be a compelling product",
        "Smart glasses launch, September 2021 (Stories), September 2023 (Ray-Ban Meta)",
        "product_delivery",
        "2023-09-27",
        True,
        "Ray-Ban Meta glasses (2023) surprised critics with quality design, good cameras, and AI features. Reviews positive. Sales exceeded expectations. Genuine product success after Portal failure.",
        "Product reviews, sales reports",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # FINANCIAL / GOVERNANCE
    # ═══════════════════════════════════════════════════════════════════
    (
        "Meta will restore profitability through cost cuts in Year of Efficiency",
        "Meta announcements, 2023",
        "financial",
        "2023-02-01",
        True,
        "Meta cut 21,000 jobs (2022-2023), reduced data center investments, and streamlined operations. Stock recovered from $88 (Nov 2022) to $300+ (2023). Profitability and margins improved dramatically.",
        "Meta financial reports, stock price",
    ),
    (
        "Giving Pledge: I will give away 99% of my wealth to philanthropy",
        "Giving Pledge commitment, December 2010; reiterated with Chan Zuckerberg Initiative, 2015",
        "personal_conduct",
        "2015-12-01",
        True,
        "Chan Zuckerberg Initiative (CZI) established with 99% of wealth pledge. Donated billions to education, health, science. Structured as LLC not foundation (criticized), but donations are real. Slow pace but commitment on track.",
        "CZI financial reports",
    ),
    (
        "Libra/Diem cryptocurrency will bank the unbanked",
        "Libra announcement, June 2019",
        "financial",
        "2019-06-18",
        False,
        "Libra/Diem faced massive regulatory backlash. Partners (Visa, Mastercard, PayPal) withdrew. Rebranded to Diem. Never launched. Project shut down January 2022. Assets sold to Silvergate. Total failure.",
        "Diem Association announcements, regulatory filings",
    ),
    (
        "We will maintain dual-class voting structure to preserve long-term vision",
        "IPO and ongoing governance, 2012-present",
        "governance",
        "2012-05-18",
        True,
        "Zuckerberg retained ~58% voting control despite owning ~13% economic stake through dual-class shares. Structure maintained through 2025. Controversial but consistently defended. Enabled long-term bets (metaverse).",
        "Meta proxy statements",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # AI
    # ═══════════════════════════════════════════════════════════════════
    (
        "We will invest in AI and open-source our models",
        "AI strategy statements, 2023",
        "ai",
        "2023-02-24",
        True,
        "Meta released LLaMA models (Feb 2023, July 2023, April 2024) as open-source. LLaMA 2 and 3 widely adopted. Major contribution to open-source AI. Competed with OpenAI/Anthropic. Genuine strategic commitment delivered.",
        "LLaMA releases, AI research community adoption",
    ),
    (
        "Meta AI will be the leading open-source AI platform",
        "Earnings calls and interviews, 2023-2024",
        "ai",
        "2023-07-26",
        True,
        "LLaMA models (especially LLaMA 3) became dominant open-source LLMs. Used by thousands of companies. Integrated into Meta products. While not leading in capabilities vs. GPT-4/Claude, led in open-source adoption.",
        "AI benchmarks, developer surveys",
    ),
    (
        "We will integrate AI across all Meta products",
        "Meta AI announcements, 2023-2024",
        "ai",
        "2023-09-27",
        True,
        "Meta AI chatbot integrated into Facebook, Instagram, WhatsApp, Messenger. Ray-Ban Meta glasses got AI features. Feed ranking improved with AI. Delivered on integration promise by 2024.",
        "Meta product releases",
    ),
    (
        "We will build massive AI infrastructure with 350K H100 GPUs",
        "Meta infrastructure announcements, 2024",
        "ai",
        "2024-01-18",
        True,
        "Meta confirmed deployment of 350K H100 GPUs by early 2024, one of world's largest AI training clusters. Enabled LLaMA 3 training. Massive capital investment delivered.",
        "Meta infrastructure blog posts",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # COMPETITION / STRATEGY
    # ═══════════════════════════════════════════════════════════════════
    (
        "Move fast and break things",
        "Original Facebook motto, 2009-2014",
        "governance",
        "2009-01-01",
        False,
        "Facebook 'broke' many things including privacy (Cambridge Analytica), mental health (teens), democracy (2016 election), and genocide prevention (Myanmar). Motto changed to 'Move fast with stable infrastructure' in 2014 but damage done.",
        "Facebook history, motto change announcement",
    ),
    (
        "We will shift to 'Move fast with stable infrastructure'",
        "Motto change, 2014",
        "governance",
        "2014-04-30",
        False,
        "Despite motto change, Facebook continued to create massive societal problems through 2016 election, Cambridge Analytica (2018), and ongoing content moderation failures. Infrastructure stabilized but external harms continued.",
        "Cambridge Analytica scandal, election interference",
    ),
    (
        "We will be transparent about how algorithms work",
        "Post-2016 election statements, 2017-2020",
        "transparency",
        "2017-09-06",
        False,
        "Algorithm transparency remained minimal. No meaningful access to ranking signals. Researchers denied data access. Leaked internal documents (Facebook Papers) revealed lack of transparency. Minor transparency reports insufficient.",
        "Facebook Papers, researcher complaints",
    ),
    (
        "We will give researchers access to data for independent study",
        "Multiple statements, 2018-2020",
        "transparency",
        "2018-09-05",
        False,
        "CrowdTangle shut down despite researcher reliance (2024). Access to API restricted. Meaningful data access denied. NYU researchers' accounts banned (2021). Transparency promises broken repeatedly.",
        "NYU Ad Observatory case, CrowdTangle shutdown",
    ),
    (
        "We will connect the world with internet.org/Free Basics",
        "Internet.org launch, 2013",
        "social_impact",
        "2013-08-20",
        False,
        "Free Basics criticized for net neutrality violations (limited, Facebook-controlled internet). India banned it (2016). Accused of digital colonialism. Program failed in most markets. Criticized by digital rights groups globally.",
        "India regulatory ruling, net neutrality advocacy reports",
    ),
    (
        "We will build data center infrastructure to support global growth",
        "Multiple announcements, 2010s",
        "product_delivery",
        "2013-01-01",
        True,
        "Meta built massive data center infrastructure in Iowa, North Carolina, Sweden, Denmark, Singapore, and other locations. Custom servers (Open Compute Project). Infrastructure scaled successfully to support 3B+ users.",
        "Data center announcements, Open Compute Project",
    ),
    (
        "Facebook ads will be transparent with 'Why am I seeing this?' feature",
        "Transparency feature announcements, 2019",
        "transparency",
        "2019-03-28",
        False,
        "Feature launched but explanations remained vague and unhelpful. Did not reveal actual data used or targeting logic. Transparency promise largely cosmetic. Users still couldn't understand ad targeting in meaningful way.",
        "User studies, privacy advocate analysis",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # ADDITIONAL STATEMENTS
    # ═══════════════════════════════════════════────────────────────────
    (
        "Instagram will never get ads",
        "Instagram co-founder statements pre-acquisition, contradicted post-acquisition",
        "product_delivery",
        "2012-04-09",
        False,
        "Instagram launched ads in 2013, just one year after acquisition. Ads became pervasive by 2020. Original promise of ad-free experience abandoned. Monetization prioritized over user experience.",
        "Instagram ad announcements",
    ),
    (
        "We will respect user privacy and not track users across the web without consent",
        "Privacy policy statements, 2010s",
        "privacy",
        "2015-01-01",
        False,
        "Facebook tracked users across the web with Like buttons, Pixel, and other tools. Shadow profiles created for non-users. Apple iOS 14.5 (2021) revealed extensive tracking. EU fined Facebook repeatedly for GDPR violations.",
        "GDPR violation fines, Apple ATT framework",
    ),
    (
        "Facebook will not use photos for facial recognition without permission",
        "Privacy statements, 2010-2015",
        "privacy",
        "2011-01-01",
        False,
        "Facebook auto-tagged photos using facial recognition without explicit consent. Illinois class-action lawsuit resulted in $650M settlement (2021). Feature eventually shut down in 2021 after years of violations.",
        "Illinois biometric privacy lawsuit settlement",
    ),
    (
        "We will label state-controlled media outlets",
        "Transparency announcement, 2020",
        "content_moderation",
        "2020-06-04",
        True,
        "Facebook began labeling state-controlled media (Russia Today, China Daily, etc.) in June 2020. Labels applied consistently. Helped users identify propaganda sources. Promise delivered.",
        "Facebook transparency reports",
    ),
    (
        "Meta Quest Pro will revolutionize remote work",
        "Meta Quest Pro launch, October 2022",
        "metaverse",
        "2022-10-11",
        False,
        "Quest Pro launched at $1,500 with poor reviews. Uncomfortable, limited battery, few use cases. Price cut to $1,000 within months. Remote work use minimal. Horizon Workrooms empty. Failed to deliver on work productivity vision.",
        "Product reviews, price cuts",
    ),
    (
        "Facebook Gaming will compete with Twitch and YouTube Gaming",
        "Facebook Gaming announcements, 2018-2020",
        "product_delivery",
        "2018-06-01",
        False,
        "Facebook Gaming never gained significant market share. Shut down standalone app in 2022. Streamers left for Twitch/YouTube. Cloud gaming service shut down. Could not compete effectively.",
        "Facebook Gaming shutdown announcements",
    ),
    (
        "Facebook News will support quality journalism",
        "Facebook News launch, 2019",
        "social_impact",
        "2019-10-25",
        False,
        "Facebook News shut down in US in 2023 after failing to gain traction. Pulled news in Canada and Australia amid disputes with governments over payment to publishers. Did not meaningfully support journalism long-term.",
        "Facebook News shutdown announcements",
    ),
]

print("=" * 70)
print("SAY/DO POC: Mark Zuckerberg Contradiction Index")
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
    ("Meta AI will be the leading open-source AI platform", "ai"),
    ("The metaverse will be mainstream within five years", "metaverse"),
    ("We will protect user privacy going forward", "privacy"),
    ("Threads will overtake Twitter/X", "product_delivery"),
    ("Ray-Ban Meta glasses will replace smartphones", "product_delivery"),
    ("We will responsibly deploy AI across all Meta products", "ai"),
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
# COMPARISON SUMMARY (if Musk data exists)
# ──────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("POC COMPLETE")
print("=" * 70)
