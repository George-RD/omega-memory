# OMEGA Brand Guide

**Status: Complete v1.0**
**Last updated: Feb 12, 2026**

> This guide defines how OMEGA speaks across every channel. Every piece of writing — README, tweet, docs, issue response, error message — should feel like it came from the same mind.
>
> Voice is constant. Tone adapts to context. (Mailchimp principle: voice doesn't change day to day, but tone changes all the time.)

---

## 0. Brand Architecture

The naming hierarchy across all surfaces:

| Layer | Name | Role | Where it appears |
|-------|------|------|-----------------|
| **Product** | **OMEGA** | The brand people say, see, and search for | README, docs, social, conversations, UI |
| **Company** | **OmegaMax** | Legal entity, org identity | Domain (omegamax.co), copyright, invoices, legal filings |
| **Package** | **omega-memory** | Technical identifier for install and discovery | PyPI, GitHub org, `pip install omega-memory` |

### Product Tiers

| Tier | Name | License | Scope |
|------|------|---------|-------|
| **Free** | **OMEGA** (or "OMEGA Core" when distinguishing) | Apache-2.0 | 27 memory tools, open source |
| **Paid** | **OMEGA Pro** | Commercial (TBD) | Coordination, routing, entity management, cloud sync |

- When referring to the product generically, say **OMEGA** — not "OMEGA Core." The free tier IS the product.
- Use "OMEGA Core" only when explicitly contrasting with OMEGA Pro (e.g., comparison tables, pricing pages).
- Use "OMEGA Pro" for the paid tier. Never "OmegaMax Pro" or "OMEGA Premium."

### Rules

1. **Product name is primary.** When referring to the product, always use OMEGA. Never OmegaMax. Never omega-memory.
2. **Company name is background.** OmegaMax appears in footers, legal text, and "by" attribution — never as the product name.
3. **Package name is technical.** omega-memory is what you type in a terminal. It does not appear in marketing, social, or docs prose.
4. **The pattern:** "OMEGA" stands alone. When attribution is needed: "OMEGA by OmegaMax." Never the reverse.
5. **Domain:** omegamax.co hosts the product — this is normal (cursor.com → Anysphere, next.js → Vercel). The domain is the company; the product name dominates the page.

### Usage Examples

| Context | Correct | Incorrect |
|---------|---------|-----------|
| README tagline | "OMEGA — persistent memory for AI agents" | "OmegaMax — persistent memory for AI agents" |
| Install instruction | `pip install omega-memory` | `pip install omega` or `pip install omegamax` |
| Tweet | "OMEGA v1.1 is live." | "OmegaMax v1.1 is live." |
| Footer / copyright | "© 2026 OmegaMax" | "© 2026 OMEGA" |
| Docs prose | "OMEGA stores memories in SQLite" | "omega-memory stores memories in SQLite" |
| GitHub bio | "OMEGA — the memory system for AI agents" | "OmegaMax memory system" |

### Precedents

- **Cursor** (product) / **Anysphere** (company) — nobody says "Anysphere"
- **Next.js** (product) / **Vercel** (company) — product name dominates
- **Supabase** — same name for both (simpler, but requires owning a single distinctive word)

---

## 1. Brand Identity

### Who We Are
OMEGA is a persistent memory and coordination system for AI agents. Open-core, local-first, privacy-respecting. Built by developers, for developers. No VC, no hype, no corporate parent.

### Brand Archetype
**The Quiet Expert.** We don't sell. We demonstrate. We don't claim — we prove. We're the senior engineer in the room who speaks rarely but precisely, and when they do, people listen.

Closest references:
- **Linear's minimalism** — say less, mean more
- **Zed's opinions** — unafraid to state what we believe
- **Resend's builder credibility** — earn trust through shipped code, not marketing copy

We are NOT:
- Supabase (too playful for a zero-audience launch)
- Mem0 (too aggressive, too many CTAs, too marketing-forward)
- Cline (too chatty, too feature-tour)

### The Pseudonymous Constraint
OMEGA launches without a face. No founder story. No "I built this." The project speaks as itself. This means:
- Voice must carry authority without personal credibility to lean on
- Every claim must be verifiable (benchmarks, code, docs)
- Trust is built through substance, not personality

Research confirms pseudonymous projects can earn more loyalty than named ones — "under certain circumstances, pseudonyms prove more stable than the persons attached to them." The mechanism: consistency over time + transparency of process + code quality as proof.

### The Trust Ladder (Pseudonymous Launch)

Trust is earned in stages. Don't skip ahead.

| Phase | Trust Mechanism | Voice Permission |
|-------|----------------|-----------------|
| **Day 1** | Code quality + docs quality IS the identity. SQLite model: 590x test-to-production ratio as implicit marketing. | Factual only. Zero personality. Let the work speak. |
| **Month 1-3** | Consistency of voice across README, docs, issues, changelog builds familiarity. | Dry wit permitted. Still no memes, no hot takes. |
| **Month 3-6** | Community engagement — responding to every issue, explaining decisions publicly — builds relationship. | Mild opinions allowed. "We chose X because Y." |
| **Month 6+** | Track record of reliability + transparent governance earns the right to personality. | Can take positions. Engage in debates. Earned irreverence. |

**The SQLite precedent**: No marketing team, no social presence, no brand guidelines. Authority comes from: most-deployed database in the world, 590x test code ratio, bugs fixed within hours, and documentation that reads like it was written by someone who has thought about every word.

**The Rust precedent**: A faceless project with genuine warmth. Empathetic *tooling* (actionable compiler errors) IS the brand voice. Your CLI output, error messages, and tool feedback are experienced more often than your README.

---

## 2. Voice Principles

### Principle 1: Technical Precision
Say exactly what it is. No abstractions, no buzzwords, no hand-waving.

| Instead of | Write |
|-----------|-------|
| "AI-powered memory solution" | "Persistent memory via SQLite + sqlite-vec" |
| "Intelligent coordination layer" | "File locking, branch claims, and task queues for multi-agent workflows" |
| "Seamlessly integrates" | "Registers as an MCP server in one command" |
| "Leverages cutting-edge AI" | (delete the sentence) |

### Principle 2: Confident Without Claiming
Use the definite article when we own the category. Use measured language when we don't.

| Confident (earned) | Overclaiming (avoid) |
|--------------------|---------------------|
| "The only MCP server with multi-agent coordination" | "The best memory system" |
| "73 tools in one install" | "The most powerful AI memory" |
| "Scores 76.8% on LongMemEval" | "Industry-leading accuracy" |
| "Zero cloud dependencies" | "Revolutionary privacy" |

### Principle 3: Show, Then Tell
Code before prose. Numbers before adjectives. Demos before descriptions.

Order of credibility:
1. Working code example
2. Benchmark number
3. Architectural fact
4. Feature description
5. Benefit statement (use sparingly)

### Principle 4: Respect the Reader's Time
Developers scan. Front-load the information they need. Cut everything else.

- Lead with the thing they can do, not what the thing is
- One concept per paragraph
- If a section doesn't help someone install, use, or evaluate OMEGA, cut it

### Principle 5: Honest About Tradeoffs
State what we don't do as clearly as what we do. Developers trust tools that acknowledge limits.

Examples:
- "76.8% on LongMemEval — competitive but not leading. Hindsight scores 91.4% on pure memory accuracy. OMEGA trades peak accuracy for integration breadth."
- "Startup memory is ~31MB, rising to ~337MB after first query (ONNX model load)."
- "The free core includes 27 memory tools. Coordination, routing, and entity management require omega-pro."

---

## 3. Voice Dimensions

Using the Nielsen Norman framework:

| Dimension | OMEGA's Position | Notes |
|-----------|-----------------|-------|
| **Funny ←→ Serious** | Serious (80%) | No jokes, no memes, no emojis in primary channels. Occasional dry wit in community spaces. |
| **Formal ←→ Casual** | Casual-professional (60% casual) | No corporate speak, but no "hey devs!" either. Write like a Hacker News comment that gets upvoted. |
| **Respectful ←→ Irreverent** | Respectful (70%) | Respect competitors and the reader. Irreverence reserved for the *problem* ("Your AI has amnesia"), never directed at people or tools. |
| **Enthusiastic ←→ Matter-of-fact** | Matter-of-fact (80%) | Let the work speak. Reserve enthusiasm for genuine milestones ("v1.0 is live"). |

### Voice in One Sentence
**OMEGA sounds like a staff engineer writing a technical RFC that happens to be public.**

### Context-Specific Voice Map

The voice stays the same. The tone dial moves.

| Context | Serious ← → Casual | Personality Level | First Priority |
|---------|--------------------|--------------------|----------------|
| **README** | 70% serious | Low — facts and code | Install command visible without scrolling |
| **Documentation** | 90% serious | Zero — Stripe model | Outcome-focused: "Here's how to X" not "Here's what X is" |
| **Error messages** | 60% serious | Empathetic, actionable | What went wrong + how to fix it. Never blame the user. |
| **Changelog** | 80% serious | Minimal personality peaks | User impact first, implementation detail second |
| **GitHub Issues** | 50/50 | Peer-to-peer, helpful | Answer first, pleasantries never |
| **GitHub Discussions** | 40% serious | Conversational, transparent | Share reasoning openly, admit uncertainty |
| **X/Twitter** | 30% serious | Highest personality | Substance first, but earned opinions welcome |
| **Discord** | 30% serious | Warmest, most human | Community-building, emojis acceptable |

**Key distinction** (from Stripe): Documentation is a **sacred zone of neutrality**. Zero marketing language. A feature is not shipped until its docs are written. This separation protects trust — devs know the docs will never sell to them.

---

## 4. Writing Rules

### Sentence Structure
- **Default to short.** 8-15 words per sentence. Break long sentences in two.
- **Active voice always.** "OMEGA stores memories" not "Memories are stored by OMEGA."
- **Fragments are fine** when they add rhythm. "No cloud required." "One pip install."
- **No hedging.** Remove "just", "simply", "easily", "really", "basically".

### Word Choice
- **Concrete nouns over abstract ones.** "SQLite database" not "storage layer."
- **Verbs over adjectives.** "Stores, queries, and coordinates" not "powerful, intelligent, seamless."
- **Numbers over claims.** "73 tools" not "comprehensive toolkit."

### Forbidden Words and Phrases

Words that "have high potential to make people feel stupid" (Google developer style guide) or signal that the writer doesn't understand the product:

| Never use | Why | Alternative |
|-----------|-----|-------------|
| "Simply" / "Just" / "Easily" | Patronizing — if it's simple, show the 3 lines of code | Show the code |
| "Obviously" | If it were obvious, you wouldn't need to say it | Remove the word |
| "Leverage" | Corporate buzzword | "Use" |
| "Seamless" | Means nothing to a developer | Describe the actual integration |
| "Revolutionary" | Unearned claim | State the fact |
| "AI-powered" | Everything is AI-powered in 2026 | Name the actual technology |
| "Cutting-edge" | Vague superlative | Cite the benchmark |
| "Unlock" | Marketing speak | "Enable" or describe what happens |
| "Game-changer" | Hyperbolic | State the impact with numbers |
| "Best-in-class" | Unverifiable | Compare with specific metrics |
| "Supercharge" | Mocked in every developer community | Describe the actual speedup |
| "Delighted to" | Faux-enthusiasm | "Releasing X" |
| "Excited to announce" | Overused, zero signal | "X is live" or "Shipping X" |
| "Hey everyone!" | Fellow-kids energy | Start with the substance |
| "Blazing fast" | Vague | "Retrieval takes ~50ms" |
| "Intelligent" (as adjective) | Marketing abstraction | Name the technique (semantic search, graph traversal) |

### We Say / We Don't Say

| We Say | We Don't Say |
|--------|-------------|
| "OMEGA persists context across sessions" | "OMEGA supercharges your AI workflow" |
| "Memory retrieval takes ~50ms" | "Blazing fast memory" |
| "73 MCP tools. One pip install." | "Comprehensive, all-in-one platform" |
| "Works with Claude Code. Extensible to other MCP clients." | "Works with every AI agent" |
| "Open core — free CLI, paid coordination and routing" | "Freemium" |
| "Here's what failed and how to fix it" (errors) | "Oops! Something went wrong" |
| "76.8% on LongMemEval. Hindsight scores 91.4%." | "Industry-leading accuracy" |
| "v1.1 is live." | "We're SO excited to announce v1.1!!" |
| Specific numbers and benchmarks | Superlatives without evidence |

### Punctuation
- **One exclamation mark** per document maximum. Prefer zero.
- **No emojis** in README, docs, blog posts, or formal communications.
- **Emojis acceptable** only in Discord community spaces and casual tweet replies.
- **Em dashes** for asides — use sparingly.
- **Colons** to introduce lists or explanations.

### Formatting Hierarchy
1. Headlines: imperative or noun phrase ("Install OMEGA", "Memory Tools")
2. Subheads: short declarative ("Your agent remembers across sessions")
3. Body: 1-3 sentences per paragraph max
4. Lists: parallel structure, front-loaded with the key word
5. Code: complete, copy-pasteable, minimal

---

## 5. GitHub Voice

### README Philosophy
OMEGA's README sits between the **Resend model** (manifesto + code) and the **Linear model** (minimal authority). Not as bare as Cursor. Not as long as Cline.

**Target length**: 400-600 words of prose (excluding code blocks and tables).

### README Structure
Based on cross-repo analysis, the highest-performing pattern for OMEGA's position:

1. **Logo + badges** (3-4 max: Python version, license, tests passing, PyPI)
2. **One-line description** (bold, under the name)
3. **Tagline paragraph** (2-3 sentences, the "why")
4. **Install block** (pip install, immediately)
5. **60-second quickstart** (real code or conversation example)
6. **Feature grid** (6 capabilities, table or bullet list)
7. **Comparison table** (OMEGA vs Mem0 vs Zep vs Letta — honest)
8. **Architecture** (ASCII diagram, brief)
9. **Tool reference** (collapsible sections by module)
10. **Footer** (contributing, license, links)

### Key Decisions
- **Article choice**: Use "The" for categories we own ("The memory system for AI agents") not "A"
- **No screenshots**: OMEGA is CLI/MCP — show terminal output, not GUIs
- **Code first**: Install command visible without scrolling
- **Comparison table**: Include it. Supabase names Firebase. We name Mem0.
- **Badges**: 3-4 max. Python version, license, tests, PyPI version. No vanity badges.
- **No "Why OMEGA" section**: The problem statement IS the why section
- **Collapsible details**: Advanced architecture, full tool reference, storage details — use `<details>` tags

### GitHub Issues Voice
- Respond within 24 hours
- Tone: helpful, direct, no corporate pleasantries
- Start with the answer, not "Thanks for opening this issue!"
- If we can't fix it: say so clearly with the reason
- Template: problem → cause → fix/workaround → timeline (if applicable)

Example:
```
The embedding model loads lazily on first query, which adds ~300MB RSS.
This is by design — it keeps startup at 31MB.

If memory is a concern, you can preload at setup time:
`omega warmup`

This will be configurable in v1.1.
```

NOT:
```
Hi! Thanks so much for reaching out about this. We really appreciate your feedback!
The memory usage you're seeing is expected behavior...
```

### GitHub Discussions Voice
- Technical, conversational, peer-to-peer
- Share implementation reasoning openly
- Admit uncertainty: "We haven't decided on X yet. Current thinking is..."
- Welcome disagreement: "That's a fair point. The tradeoff we chose was..."

### Commit Messages
- Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`
- Imperative mood: "Add graph traversal" not "Added graph traversal"
- Body explains *why*, not *what* (the diff shows what)

### Release Notes / Changelog
- Lead with the user impact, not the implementation detail
- Group by: Added, Changed, Fixed, Removed
- One line per change, link to PR/issue
- No marketing language in changelogs — just facts

Example:
```
## v1.1.0

### Added
- `omega_traverse`: Walk the memory relationship graph (up to 5 hops)
- `omega_compact`: Cluster and summarize related memories
- Context virtualization: checkpoint/resume across sessions

### Fixed
- Dedup threshold was too aggressive at 0.90 (lowered to 0.85)
- Session heartbeat race condition on fast reconnects

### Changed
- Default retrieval limit increased from 5 to 10 results
```

---

## 6. X/Twitter Voice

### Account Strategy

**Account type**: Project account (@omega_memory or similar), not a personal account.

The pseudonymous constraint means we can't use the founder-amplification strategy that works for Resend (Zenorocha has 56.7K followers, @resend has 1.7K — a 33:1 ratio). Project accounts grow 5-10x slower than founder accounts. OMEGA must compensate with:
- Higher content quality per tweet
- More aggressive engagement (replies, quote-tweets)
- Visual consistency (every tweet with media)
- Reliability of cadence (weekly changelog rhythm)

### Bio

**Formula**: [What it is] + [Key differentiator] + [Link]

Candidates (modeled on top performers):
- `"The memory system for AI agents. 73 MCP tools. Local-first, open-core."` (Mem0 model: category + numbers)
- `"Persistent memory for AI agents. Zero cloud. One pip install."` (Zed model: claim + differentiator)
- `"Your AI forgets everything between sessions. OMEGA doesn't."` (problem-first — risky for a bio, stronger as a pinned tweet)

**Reference bios from research:**
| Account | Followers | Bio | Words | Style |
|---------|-----------|-----|-------|-------|
| @supabase | ~292K | "Build in a weekend. Scale to millions." | 8 | Outcome statement |
| @linear | ~83K | "Purpose-built for planning and building products" | 14 | Category + function |
| @vercel | ~167K | "The platform for frontend developers..." | 17 | Category claim + OSS name-drop |
| @cursor_ai | ~150K+ | "The AI Code Editor" | 4 | Ultra-minimal |
| @raycastapp | ~85K | "Your shortcut to everything" | 4 | Metaphor |
| @zeddotdev | ~65K | "A next-generation code editor..." | 14 | Category + differentiators |
| @mem0ai | ~11K | "The Memory Layer for your AI apps" | 7 | "The X for Y" + YC badge |
| @resend | ~15-25K | "Email for developers" | 3 | "[Thing] for [audience]" |

**Pattern**: The most successful bios are 3-8 words. They claim a category or state an outcome. None list features.

**Bio options for OMEGA (ranked):**
1. `Persistent memory for AI agents. Open source.` (Resend pattern — direct, signals trust)
2. `The memory layer for AI agents.` (Mem0-adjacent but differentiated by being local-first)
3. `Give your AI agents memory that persists across sessions.` (Supabase outcome pattern)

**OMEGA decision**: Option 1. "Persistent memory for AI agents. Open source." — 7 words, signals what it is + differentiator. Add "Local-first" to bio as it evolves. Keep following count low (<50) to signal focus.

**Additional account setup:**
- **Profile picture**: Logo/icon (every project account uses a logo, not a face)
- **Header image**: Dark-themed terminal screenshot showing OMEGA in action
- **Pinned tweet**: Problem-statement + concrete metrics once available
- **Link in bio**: GitHub repo (not docs, not landing page — repo is the product)

### Voice Archetype for X

Based on the 8-account analysis, OMEGA maps to a hybrid:

| Archetype | Account | What OMEGA takes |
|-----------|---------|-----------------|
| **Quiet Authority** | Linear | Restraint, no emojis, "Introducing X" format, quality over quantity |
| **Technical Expert** | Mem0 | Benchmarks, educational content, "how it works" threads |
| **Builder-in-Public** | Resend/Zenorocha | Shipping updates with context, honest about tradeoffs |

We are NOT:
- Supabase (memes require existing audience + authentic humor DNA)
- Cursor (near-silence requires existing virality)
- Vercel (event-centric model requires budget and speakers)

### Content Mix

| Type | % | Examples |
|------|---|---------|
| **Product updates** (changelogs, features, demos) | 40% | "v1.1 is live. Graph traversal, memory compaction, and context checkpoints." |
| **Technical education** (how it works, architecture) | 20% | "OMEGA's retrieval pipeline: vector similarity + FTS5 + type weighting + contextual reranking. Here's how they combine:" |
| **Industry commentary** (AI memory landscape, MCP) | 15% | "Claude Code burns 14K tokens loading MCP tool descriptions before a conversation starts. Context management is the next frontier." |
| **Community engagement** (RT users, reply to questions) | 15% | Retweet every mention. Reply to every question. |
| **Benchmark/data** (numbers, comparisons) | 10% | "76.8% on LongMemEval. Here's what each category tells us about retrieval quality." |

### Tweet Formats (Modeled on Actual Patterns)

**Feature announcement (Linear model):**
```
Introducing omega_traverse.

Walk the memory relationship graph — up to 5 hops,
filtered by edge weight.

Discover how memories connect across sessions.

[link to docs]
[terminal screenshot]
```

**Changelog (Linear model):**
```
This week:

- omega_compact: cluster and summarize related memories
- Dedup threshold relaxed (0.90 → 0.85)
- Session heartbeat race condition fixed

[link to CHANGELOG.md]
```

**Technical insight (Mem0/Zep model):**
```
Context windows are buffers, not memory.

200K tokens sounds like a lot until you load 50 MCP tools
(~100K tokens) and your session history (~60K).

That leaves ~40K for actual work.

OMEGA moves long-term context out of the window
and into a searchable, persistent store.
```

**Benchmark (Mem0 model, but without the emojis):**
```
LongMemEval results (500-question evaluation):

OMEGA: 76.8%
Zep/Graphiti: 71.2%
Full-context GPT-4o: 63.8%

Hindsight leads at 91.4% — but does memory only.
OMEGA adds 27 coordination tools and local-first privacy.

Detailed breakdown: [link]
```

**Build-in-public (Zenorocha model, adapted for pseudonymous):**
```
Shipped omega_checkpoint this week.

The problem: context windows fill up mid-task.
You lose your plan, your progress, your decisions.

Now OMEGA can snapshot task state and resume in a new session
with full working memory.

Took three iterations to get the serialization right.
```

### Voice Rules for X

1. **No emojis in tweets.** Linear model, not Mem0. Zero emojis in tweet body. Occasional functional emoji acceptable in replies only.
2. **One media per tweet.** Terminal screenshot, code snippet image, or architecture diagram. Visual tweets get 2-3x engagement. Never tweet text-only.
3. **Never start with "We're excited to..."** or "Thrilled to share..." Start with the thing itself.
4. **No hashtags.** Hashtags signal marketing, not substance. Exception: #MCP in rare cases where discoverability matters.
5. **No threads over 5 tweets.** Respect attention spans. If it needs more than 5, write a blog post and tweet the link.
6. **Lead with the insight.** First sentence must deliver value. No throat-clearing.
7. **Reply to everything for the first 12 months.** Every mention, every question, every criticism. This is how pseudonymous projects build trust.
8. **Engage 2x for every tweet posted.** For every original tweet, make 2 substantive replies in AI memory / MCP / developer tooling discussions.
9. **Weekly changelog cadence.** Post a changelog tweet every week, same day. Creates reliability. People learn when to check.
10. **No retweet without comment.** Always add context when amplifying.

### Algorithm Facts (2025-2026)

These are verified from X's open-source algorithm code and updated for the March 2026 changes:

| Action | Weight (vs Like = 1x) |
|--------|-----------------------|
| Reply that gets a reply back | **75x** |
| Repost (retweet) | **20x** |
| Reply | **13.5x** |
| Profile visit + like/reply | **12x** |
| Click into conversation + engage | **11x** |
| Bookmark | **10x** |
| Like | **1x** (baseline) |

**Critical: Link suppression (March 2026).** Non-Premium link posts get near-zero distribution. Never post "Check out our blog: [link]" as the main content. Write natively, put links in reply or bio.

**Implications for OMEGA:**
1. **Get X Premium.** 2-4x visibility boost. Non-negotiable for a zero-follower launch.
2. **Reply to every comment in the first 30 minutes** (75x multiplier on reply-to-reply).
3. **Post between 10 AM - 1 PM PST, Tue-Thu** (peak developer engagement window).
4. **Write content natively** — code screenshots instead of links to docs. Blog content as threads, not link posts.
5. **Threads (3-5 tweets)** get +40-60% impressions vs standalone. 63% more likely to be retweeted.
6. **Images** get +150% retweets vs text-only. Every tweet needs a visual.

### Posting Cadence

| Phase | Frequency | Focus |
|-------|-----------|-------|
| **Week 1** (pre-launch, 0 followers) | 0 original posts. 10-15 replies/day on AI memory/MCP discussions. | Build presence through valuable comments on larger accounts. |
| **Week 2** | 1 original post (problem-statement, no product). 10+ replies/day. | Educational thread about AI memory pain points. |
| **Week 3** (soft launch) | 1 post/day. 10+ replies/day. | First product mention as "here's what I built" with screenshot. No external link. |
| **Steady state** | 3-5 original/week. Engage 2x per post. | Mix per content ratio above. |
| **Launch Week events** | Daily for 3-5 days. | One feature per day, Supabase model. |

**The 80/20 rule until 500 followers**: 80% engagement (replies on others' posts), 20% original content. Invert this ratio only after organic reach is established.

### The Pseudonymous Gap

Without a founder account, OMEGA loses the 33:1 amplification that Resend, Mem0, and others get. Compensate by:

1. **Making the project account feel human.** Use "I" sparingly in replies (the maintainer speaking), "OMEGA" in announcements.
2. **Building relationships with developers who cover AI tools.** Engage in their replies. Provide genuine value. Don't pitch.
3. **Creating a consistent visual identity.** Dark-themed terminal screenshots, consistent color accent, recognizable at a glance in a feed.
4. **Leveraging the product as content.** Every demo IS a tweet. Every benchmark IS a tweet. Every bug fix IS a tweet.

### What NOT to Do on X

| Anti-Pattern | Why | Example |
|-------------|-----|---------|
| Memes before you have an audience | Forced humor is the fastest way to lose credibility | A DevOps tool's "dank CI/CD memes" with 50 followers |
| Cursor-level silence | Only works if product is already viral | Tweeting once a month with zero existing users |
| Emoji-heavy announcements | Signals marketing, not engineering | "🚀🔥 HUGE update!! 🎉🎊" |
| Giveaways / engagement bait | Attracts wrong audience, zero conversion | "Like + RT for a chance to win..." |
| Subtweet competitors | Comes across as insecure | "Unlike SOME memory tools, we actually work offline..." |
| Auto-posting from other platforms | Feels robotic, algorithm penalizes | Cross-posted LinkedIn content |

---

## 7. Docs Voice

### Philosophy
Docs are the #1 driver of developer adoption. They are where developers spend time, what AI assistants pull from, and what determines whether someone stays or leaves. Treat docs as product, not afterthought.

**Model: Stripe.** 100% neutral brand voice. Zero marketing language. Outcome-focused framing ("Here's how to persist a decision across sessions" not "Here's the omega_store API"). A feature is not shipped until docs are written.

### Docs Writing Rules (adapted from Vercel + Stripe)
- **Active voice always.** "Install the CLI" not "The CLI will be installed."
- **Second person ("you").** "You can query memories with..." not "Users can query..."
- **Action-oriented.** Lead with what the reader will accomplish.
- **As few words as possible.** If you can cut a word without losing meaning, cut it.
- **Consistent terminology.** Introduce as few unique terms as possible. Once you call it a "memory," never switch to "record" or "entry."
- **No personality.** No jokes, no asides, no brand expression. The absence of personality IS the personality — it says "we respect your time."
- **Error messages alongside solutions.** Every error a user might see, documented with the fix.
- **Code examples are complete.** Copy-paste should work. No "..." elisions in critical paths.

### Page Template
```
# [Tool/Feature Name]

[One sentence: what this does and when to use it]

## Quick Start
[Minimal working code — copy-pasteable]

## Parameters
[Table: name, type, required, description, default]

## Examples
[2-3 real-world patterns, each with context sentence + code]

## Common Errors
[Error message → cause → fix, for each known error]
```

### Error Message Voice (Rust Model)

Error messages are experienced more often than any other writing. They ARE the brand for most users.

**Pattern**: What happened + Why + How to fix it

Good:
```
Memory graph not found at ~/.omega/omega.db
Run `omega setup` to initialize the database.
```

Bad:
```
Error: Database not found
```

Worse:
```
Oops! Something went wrong. Please try again later.
```

**Rules for error messages:**
- Never blame the user ("You entered an invalid..." → "Expected a valid...")
- Always include the actionable next step
- Show the specific path/value that caused the error
- Positive framing: "Run X to fix" not "You forgot to run X"

---

## 8. Competitive Mentions

### Rules for Naming Competitors
1. **Name them in comparison tables.** Vague "other tools" is less credible than "Mem0 does X, we do Y."
2. **Be factually accurate.** Every claim about a competitor must be verifiable.
3. **Acknowledge their strengths.** "Mem0 has 44K GitHub stars and deep AWS integration."
4. **Differentiate on facts, not feelings.** "Mem0 is memory-only. OMEGA adds coordination, routing, and entity management."
5. **Never disparage.** No "unlike the competition" energy. State facts.
6. **Update regularly.** Competitors ship fast. A stale comparison destroys credibility.

### Positioning by Competitor

| vs Mem0 | "Mem0 does memory well. OMEGA does memory + coordination + routing + knowledge in one install." |
| vs Zep/Graphiti | "Zep requires Neo4j. OMEGA uses SQLite. Both do knowledge graphs — different infrastructure tradeoff." |
| vs Letta | "Letta is a stateful agent platform. OMEGA is a memory layer that works with any agent. Different scope." |
| vs native memory | "Claude's built-in memory is basic key-value. OMEGA is semantic search + graph + coordination + encrypted vault." |

---

## 9. Brand Don'ts (Anti-Patterns with Real Examples)

### Voice Anti-Patterns

1. **Don't anthropomorphize OMEGA.** It's a tool, not a character. No "OMEGA thinks" or "OMEGA believes." Say "OMEGA stores" or "OMEGA retrieves." (Compare: Cline uses "he" pronouns for the agent. We don't.)

2. **Don't use "we" in the README.** The README is a technical document. Use "OMEGA does X" or imperative "Install with pip." Use "we" only in community spaces (Discord, Discussions) once there IS a community.

3. **Don't hype launches.** "v1.1 is live" not "We're SO excited to announce v1.1!!" Research: "Developers have heard these promises before. It's never simple, easy, or scalable. There's always a trade-off."

4. **Don't pretend to be bigger than we are.** No "trusted by thousands of developers" until it's true. Use verifiable metrics only. The fastest way to lose developer trust is an unverifiable claim.

5. **Don't gate content.** No email signups to access docs. No "contact us for pricing." Developer skepticism spikes at forms — "you'll get a fake email if you get anything at all."

6. **Don't chase trends.** No "vibe coding" takes, no meme formats, no trending audio. Substance is the brand. (Note: Zed's CONTRIBUTING.md says "it's unlikely we'll merge a vibe-coded PR" — that's the level of opinion we can eventually earn.)

7. **Don't over-explain.** Assume the reader is a competent developer. Nobody reading an MCP server README needs "AI stands for Artificial Intelligence."

8. **Don't use first person plural until there's a community.** "OMEGA" or "the project" — not "we" or "our team." Shift to "we" once there are real contributors.

### Marketing Anti-Patterns (Real Failures)

These are documented failures from the developer tool space:

| Anti-Pattern | What Happened | Lesson |
|-------------|--------------|--------|
| **"Supercharge your delivery"** | A DevOps tool launched with this tagline. Ignored by developers. A competitor who said "CI/CD that doesn't make you want to quit your job" got all the attention. | Problem > solution > adjectives. |
| **"Write your code for you"** | An AI coding assistant made this promise, couldn't deliver, got mocked on Reddit, had to pivot entire messaging. | Never promise more than the product delivers. |
| **Sleek website, bad docs** | A well-funded cloud platform launched beautiful marketing but unusable documentation. Developers posted complaints on Stack Overflow. Reputation destroyed within months. | Docs > marketing site. Always. |
| **Gated OSS docs** | Multiple dev tools requiring sign-up to read documentation. Developer conversion: fake emails, immediate churn. | Never gate docs. Ever. |
| **Marketing in the wrong places** | Dev tools running Google Ads and LinkedIn campaigns. Developers live on GitHub, HN, and Discord. "If you're not engaging where they already hang out, you don't exist." | Be where developers already are. |
| **Ignoring community** | A front-end framework with good tech but no engagement on issues or discussions. Alternative that responded to every issue became the default choice. | Response time on issues > feature count. |

---

## 10. Voice Test

Before publishing anything, ask:

1. **Would this get upvoted on Hacker News?** (Technical substance, no marketing fluff)
2. **Could a competitor quote this against us?** (If yes, remove the overclaim)
3. **Does this respect the reader's time?** (If it takes 30 seconds to get to the point, cut the first 29)
4. **Is every claim backed by code, data, or a link?** (If not, add the proof or remove the claim)
5. **Would I cringe reading this in 2 years?** (If yes, tone it down)

---

## Appendix A: GitHub README Research Data

Cross-analysis of 8 developer tool READMEs. Raw data informing decisions in Section 5.

### Tagline Patterns

| Repo | Tagline | Words | Article |
|------|---------|-------|---------|
| Supabase (97K stars) | "The Postgres development platform" | 4 | **The** (category ownership) |
| Mem0 (47K stars) | "The Memory Layer for Personalized AI" | 6 | **The** (category ownership) |
| Zed (75K stars) | "A high-performance, multiplayer code editor" | 6 | **A** (category placement) |
| Cline (57K stars) | "An AI assistant that can use your CLI aNd Editor" | 10 | **An** (category placement) |
| React Email (18K stars) | "The next generation of writing emails" | 6 | **The** (generational claim) |
| Linear (1.2K stars) | "The purpose-built tool for planning and building products" | 8 | **The** (definite, singular) |
| Cursor (32K stars) | "An AI code editor and coding agent" | 7 | **An** (understated) |
| Raycast (7K stars) | "Control your tools with a few keystrokes" | 8 | (imperative — no article) |

**Pattern**: 4-10 words. "The" claims ownership. "A/An" places in category. Never starts with "We" or "Our."
**OMEGA decision**: Use "The" — "The memory system for AI agents."

### README Length Spectrum

```
Cursor:       ~40 words   ← anti-README (product sells itself)
Raycast:      ~150 words  ← routing hub
Zed:          ~200 words  ← routing hub + culture
Linear:       ~350 words  ← monorepo docs
React Email:  ~400 words  ← manifesto + components
Mem0:         ~600 words  ← marketing + quickstart
Supabase:     ~800 words  ← comprehensive platform overview
Cline:        ~1000 words ← visual feature tour
```

**OMEGA decision**: 400-600 words. Between Resend (manifesto + code) and Linear (minimal authority). Enough to convey scope (73 tools) without Cline-level feature tour.

### Code Example Placement

| Repo | First Code | Lines | Style |
|------|-----------|-------|-------|
| Resend Node SDK | After 2 headings | 5 lines | Install + minimal usage |
| React Email | After "Getting Started" | 8 lines | JSX component |
| Mem0 | After quickstart section | ~25 lines | Full working chat |
| Linear, Supabase, Cursor, Zed, Raycast, Cline | None | — | Link to docs/website |

**Pattern**: SDKs and libraries lead with code. Products and editors lead with visuals or links.
**OMEGA decision**: Lead with code. OMEGA is infrastructure (more SDK than product). Show `pip install` + conversation example within first scroll.

### Badge Count

| Repo | Badges | Types |
|------|--------|-------|
| Mem0 | 6 | Discord, downloads, commits, versions, YC |
| Linear | 5 | License, 4x CI status |
| Raycast | 2 | Twitter, Slack |
| Zed | 2 | Custom badge, CI |
| Supabase, Cursor, React Email, Cline | 0 | — |

**OMEGA decision**: 3-4 max. Python version, Apache-2.0 license, tests passing, PyPI version. No vanity badges, no YC-style credibility badges (we have none).

### Comparison Table Usage

Only Supabase names a competitor directly ("features of Firebase"). Mem0 compares against "OpenAI Memory" in metrics. Most repos avoid comparisons entirely.

**OMEGA decision**: Include comparison table. Name Mem0, Zep, Letta by name. Be honest about their strengths. This is a differentiator — most tools are afraid to name names. Research shows direct comparison is more credible than vague "other tools."

### CONTRIBUTING.md Tone Spectrum

| Most opinionated | Zed: "we tend to only merge about half the PRs" / "unlikely we'll merge a vibe-coded PR" |
| Most structured | Cline: changeset workflow, version semantics, platform setup |
| Most warm | Mem0: "Let us make contribution easy, collaborative and fun" |
| Most firm | Supabase: "PRs without clear problem statements will be closed" |
| Most minimal | Raycast: 4 sentences linking to external guides |

**OMEGA decision**: Between Zed (opinionated) and Supabase (firm). Set clear expectations. Explain the bar. Be direct about what gets merged and what doesn't.

### Universal Observations (What ALL Top Repos Do)

1. None include pricing in the README
2. None include testimonials or user quotes
3. None use "best" or superlative marketing language
4. None mention investors (except Mem0's YC badge)
5. None have FAQ sections
6. None have "vs." comparison sections (only inline)

### Voice Differentiators (What Sets Each Apart)

| Repo | Distinctive Move |
|------|-----------------|
| **Cursor** | Radical minimalism — 40-word README for the fastest-growing AI tool |
| **Zed** | Cultural opinions in CONTRIBUTING.md — defines who they are through merge policy |
| **Resend** | Manifesto energy — "we need to stop developing emails like 2010" |
| **Supabase** | Platform completeness — checkbox tracker showing everything built |
| **Mem0** | Metrics aggression — "+26% vs. OpenAI Memory" right at the top |
| **Cline** | Visual feature tour — alternating screenshots, anthropomorphized agent |
| **Linear** | Institutional silence — no product screenshots, no "why us" |

**OMEGA's distinctive move**: The honest comparison table. No other memory system includes a feature matrix that names competitors and acknowledges their strengths. Combined with benchmark numbers, this becomes "the README that tells the truth."

---

## Appendix B: Brand Framework References

### Nielsen Norman Four Dimensions of Tone
- Source: nngroup.com/articles/tone-of-voice-dimensions (2016)
- Finding: Casual + enthusiastic = most friendly and trustworthy for general audiences. For dev tools, matter-of-fact + respectful = most trusted.

### Mailchimp Content Style Guide
- Source: styleguide.mailchimp.com (Creative Commons)
- Key: Empower / Respect / Educate / Guide framework. Voice = constant, Tone = contextual.

### Stripe Documentation Culture
- Source: slab.com/blog/stripe-writing-culture
- Key: Zero marketing in docs. Docs as "part of done." CEO writes. Writing classes at onboarding.

### Google Developer Documentation Style Guide
- Source: developers.google.com/style/word-list
- Key: Comprehensive word list. Avoid "simply," "easy," "obviously."

### Vercel Writing Guidelines
- Source: vercel.com/design/guidelines
- Key: Active voice, action-oriented, second person, as few words as possible.

### Markepear Dev Tool Branding
- Source: markepear.dev/blog/branding-personality-tone-and-assets
- Key: Three axes — brand story + core values + brand personality. Spectrum: Friend/Authority, Playful/Serious, Rebel/Conventional.

---

## Appendix C: X/Twitter Research Data

Cross-analysis of 8 developer tool X accounts + 5 solo/pseudonymous founders. Full analysis at `~/Desktop/devtool-twitter-voice-analysis.md`.

### The Voice Spectrum (Loudest → Quietest)

| Account | Followers | Voice | Emojis | Frequency | Memes |
|---------|-----------|-------|--------|-----------|-------|
| Supabase | ~292K | Playful, meme-driven | Heavy | 1-3/day | Core strategy |
| Vercel | ~167K | Confident, DX-obsessed | Moderate | 1-3/day | None |
| Cursor | ~150K+ | Near-silent, understated | Zero | 2-4/month | 0% |
| Raycast | ~85K | Premium, polished | Structured | 3-5/week | None |
| Linear | ~83K | Minimal, precise, design-IS-brand | Near-zero | 2-5/week | 0% |
| Zed | ~65K | Speed-obsessed, engineering-proud | Minimal | 2-4/week | None |
| Mem0 | ~11K | Benchmark-driven, celebratory | Heavy | 4-7/week | Rare |
| Resend | ~15-25K | Official/formal (founder carries voice) | Minimal | 3-5/week | Rare |

### Launch Announcement Patterns

| Account | Structure |
|---------|-----------|
| **Linear** | "Introducing [Feature]. [One sentence]. [Link]. [Screenshot]." — single tweet, no hype |
| **Supabase** | Teaser → daily drops at 8AM PT → thread → recap → meme closer |
| **Vercel** | Pre-event hype → live countdown → numbered recap thread → "how we built" follow-up |
| **Raycast** | "Introducing [Feature]" + emoji bullet list + polished demo video |
| **Mem0** | "We're excited to announce..." + specific metric + use case + link |
| **Cursor** | "[Product] [version] is out now! [One sentence]. [Link]." — that's it |

### Founder vs. Project Account (The 33:1 Gap)

| Metric | Founder (@zenorocha) | Project (@resend) |
|--------|---------------------|-------------------|
| Followers | 56,700 | 1,700 |
| Voice | First person, narrative, vulnerable | Third person, official, formal |
| Engagement | Higher per-tweet | Lower per-tweet |
| Growth rate | Faster (humans follow humans) | Slower (brands follow brands) |

Every successful dev tool runs BOTH in parallel. OMEGA's pseudonymous constraint means the project account must compensate with higher content quality and more aggressive engagement.

### Content Ratios from Top Accounts

| Account | Product Updates | Education | Community | Industry | Fun/Memes |
|---------|----------------|-----------|-----------|----------|-----------|
| Supabase | 30% | 15% | 15% | 10% | 20% |
| Linear | 60% | 20% | 10% | 10% | 0% |
| Mem0 | 30% | 25% | 15% | 20% | 10% |
| Raycast | 35% | 25% | 15% | 10% | 15% |
| Cursor | 40% | 20% | 20% | 20% | 0% |

### Algorithm Multipliers

| Signal | Weight |
|--------|--------|
| Reply-to-reply | 75x |
| Repost | 20x |
| Reply | 13.5x |
| Profile visit + engage | 12x |
| Bookmark | 10x |
| Like | 1x |

**March 2026 change**: External links get -50% to -90% reach for non-Premium accounts. Write natively. Links in replies only.

### Solo/Pseudonymous Founder Comparison

| Account | Followers | Style | Key Tactic |
|---------|-----------|-------|------------|
| @levelsio | ~792K | Casual, revenue screenshots | Radical transparency + product shotgun approach |
| @marc_louvion | ~100K+ | Entertaining, self-deprecating | Humor as distribution + YouTube as flywheel |
| @zenorocha | ~56.7K | Builder-narrative, transparent | OSS credibility (Dracula, React Email) → paid product |
| @paulgauthier | ~16K+ | Purely technical, changelog-as-tweets | Benchmark results as primary content |
| @taranjeetio | ~13.6K | Mission-driven, metrics + philosophy | Vision posts ("Intelligence needs memory") + funding metrics |

### Sources
- Markepear: How to market to developers on Twitter (Supabase analysis)
- Craft Ventures: Inside Supabase's Breakout Growth
- Raycast Blog: The Hype Team
- Typefully x Raycast: Content Management Optimization
- Avenue Z: 2025/2026 X Twitter Organic Social Media Guide
- Tweet Archivist: How the Twitter Algorithm Works in 2026
- SocialBee: Understanding the X Algorithm in 2026
- Calmops: Twitter Growth 0 to 1000 Followers
- FounderBrands: How to Grow 0 to 1000 X/Twitter Followers
- Actual X profiles of all 8 accounts + 5 founders

---

*This is a living document. Update as voice evolves with community feedback.*
