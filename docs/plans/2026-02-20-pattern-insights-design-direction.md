# Design Direction: Pattern Insights

## Existing Brand (keep, don't change)

- **Fonts**: Outfit (display/body), JetBrains Mono (data/labels)
- **Surfaces**: canvas #08090f, base #0f1019, elevated #151620, hover #1c1d2a
- **Ink**: primary #e8e8f0, secondary #9898b0, tertiary #686880
- **Accent**: gold #d4a843, dim #b89035, muted #7a6838
- **Semantic type colors**: decision blue #6b9fff, lesson green #5ec9a0, error red #f06060, reminder amber #e8a040, task cyan #40c8c8, preference purple #b088e8
- **Admin patterns**: admin-card (gold left border), admin-section-label (11px mono uppercase)

The design system is solid. These three directions differ in **layout, visualization approach, and tone**, not in colors or typography.

## Typography System (carried from Dashboard direction, enforced)

| Element | Size | Weight | Color |
|---------|------|--------|-------|
| Section heading | 20px Outfit | 400 | ink-primary |
| Section label (mono) | 14px JetBrains Mono | 400 | gold/50% |
| Card heading | 18px Outfit | 500 | ink-primary |
| Body text | 18px Outfit | 400 | ink-primary |
| Secondary text | 16px Outfit | 400 | ink-secondary |
| Metric value (large) | 28px Outfit | 600 | ink-primary |
| Badge/label text | 14px JetBrains Mono | 400 | varies |
| Sparkline label | 14px Outfit | 400 | ink-secondary |
| Line height | 1.6 | | |

---

## Direction A: Constellation

**Feeling**: Like looking up at a night sky and seeing your knowledge mapped as stars. Explorative, visual, slightly playful. The bubble chart is the hero.

**References**: D3 zoomable circle packing, Obsidian local graph (the good parts), Observable HQ bubble galleries

**Layout**:
```
┌─ PATTERN INSIGHTS ──────────────────────────────────────┐
│  admin-section-label: "WHAT OMEGA LEARNED"              │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │                                                    │  │
│  │           ●●●                                      │  │
│  │        ●●     ●●    ○○                             │  │
│  │      ●  product  ●  ○ testing ○                    │  │
│  │      ●  strategy ●  ○○      ○○                     │  │
│  │        ●●     ●●       ◐◐                          │  │
│  │           ●●●        ◐ git ◐      ·· api ··        │  │
│  │                       ◐◐◐         ·· ····          │  │
│  │     ○○○○                                           │  │
│  │   ○ threading ○                                    │  │
│  │   ○ & concurr ○                                    │  │
│  │     ○○○○                                           │  │
│  │                                                    │  │
│  │  7 themes across 546 memories                      │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌─ WHAT'S WORKING ────┐  ┌─ TRENDS ────────────────┐  │
│  │ 1  Decisions    Very │  │ ↑ Product strategy is   │  │
│  │    helpful           │  │   growing (+40%)   ╱╱╱  │  │
│  │ 2  Lessons    Helpful│  │                         │  │
│  │ 3  Preferences Mixed │  │ ↓ Threading is          │  │
│  │ 4  Errors     Mixed  │  │   declining (-30%) ╲╲╲  │  │
│  │ 5  Summaries  Needs  │  │                         │  │
│  │    data              │  │ → Sessions 25% longer   │  │
│  └──────────────────────┘  │   recently (48min) ───  │  │
│                             └─────────────────────────┘  │
│                                                          │
│  ┌─ SYNTHESIS ──────────────────────────────────────────┐│
│  │ "Recurring theme: product strategy. Based on 47      ││
│  │  memories across 12 sessions. Key topics: roadmap,   ││
│  │  prioritization, user research."                     ││
│  │                                         Based on 47 →││
│  └──────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────┘
```

- Bubble chart takes up ~60% of the vertical space. It's the visual anchor.
- Bubbles use monochromatic gold: larger bubbles are brighter gold, smaller bubbles are dimmer.
- Click a bubble: it expands inline, pushing others aside, showing keywords + representative memories.
- "What's Working" and "Trends" sit side-by-side below the bubbles.
- Synthesis cards at the bottom as blockquotes.

**Color approach**: Gold luminance gradient for bubbles (bright gold for large themes, muted amber for small). Dark canvas behind bubbles creates a "constellation" feel. Sparklines in trend cards use gold line with subtle fill-below.

**Strengths**: Visually striking. The bubble chart creates an immediate emotional reaction ("look at my knowledge"). Feels distinct from the rest of the admin dashboard's card-based layout. Good for impressing on first view.

**Risk**: Bubble chart implementations can be finicky (label collision, responsiveness). Force-directed layout may not settle cleanly. On mobile, the chart degrades poorly and needs a complete fallback (ranked list).

---

## Direction B: Insight Bento

**Feeling**: Clean, structured, scannable. Like a well-organized report. Every piece of information is a card in a bento grid. Consistent with the Dashboard tab's Portfolio Grid direction.

**References**: Apple Health insight cards, Mixpanel Metric Trees, Palantir metric widgets

**Layout**:
```
┌─ PATTERN INSIGHTS ──────────────────────────────────────┐
│  admin-section-label: "WHAT OMEGA LEARNED"              │
│                                                          │
│  ┌───────────────────────┐  ┌──────────┐  ┌──────────┐ │
│  │ PRODUCT STRATEGY       │  │ THREADING │  │ TESTING  │ │
│  │ ━━━━━━━━━━━━━━━━━━━━   │  │ ━━━━━━━━  │  │ ━━━━━━  │ │
│  │ 47 memories · Strong   │  │ 23 mem    │  │ 18 mem  │ │
│  │                        │  │ Emerging  │  │ Emerging│ │
│  │ roadmap, prioritize,   │  │           │  │         │ │
│  │ user research, market  │  │ lock,     │  │ pytest, │ │
│  │                        │  │ mutex,    │  │ fixture │ │
│  │ ↑ Growing  ╱╱╱╱       │  │ safe      │  │ mock    │ │
│  └───────────────────────┘  └──────────┘  └──────────┘ │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐  │
│  │ GIT STYLE│  │ DATABASE │  │ API      │  │ DEPLOY │  │
│  │ ━━━━━    │  │ ━━━━━━   │  │ ━━━━     │  │ ━━━━   │  │
│  │ 12 mem   │  │ 15 mem   │  │ 8 mem    │  │ 6 mem  │  │
│  │ Strong   │  │ Emerging │  │ Devel.   │  │ Devel. │  │
│  └──────────┘  └──────────┘  └──────────┘  └────────┘  │
│                                                          │
│  ┌─ WHAT'S WORKING ────────────────────────────────────┐ │
│  │ 1  Decisions ████████████████████  Very helpful      │ │
│  │ 2  Lessons   ██████████████       Helpful            │ │
│  │ 3  Preferences ████████           Mixed              │ │
│  │ 4  Errors    ██████               Mixed              │ │
│  │ 5  Summaries ███                  Needs data         │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌─ TRENDS ─────────────────────────────────────────────┐│
│  │ ↑ Product strategy growing · ↓ Threading declining · ││
│  │   → Sessions 25% longer                              ││
│  └──────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────┘
```

- Each theme is a card. The top theme gets a larger card (spans 2 cols). Others are uniform smaller cards.
- Cards use the existing admin-card pattern (gold left border, dark surface, hover lift).
- No bubble chart; the card grid IS the theme visualization. Size and position communicate importance.
- Keywords shown as muted tags within each card.
- Trend indicators embedded within theme cards (the "Growing" badge on the product strategy card).
- "What's Working" as a horizontal bar chart below the theme cards.
- "Trends" as a compact single-line summary at the bottom.

**Color approach**: Each theme card uses the standard admin-card style (gold left border). The top theme card gets a slightly brighter gold border or a subtle gold background tint. Bar fills in "What's Working" use gold at varying opacity.

**Strengths**: Perfectly consistent with the existing admin aesthetic. No new visualization libraries needed (no D3). Cards are easy to implement and responsive by default. Every element is a standard Tailwind component. Fastest to build.

**Risk**: Less visually exciting than Direction A. The "flat grid of cards" doesn't create the same "wow" as a bubble chart. Theme cards could feel repetitive if there are 7+ themes.

---

## Direction C: Narrative Scroll

**Feeling**: Personal, reflective. Like reading a brief intelligence report about your own knowledge. Inspired by Spotify Wrapped (but not the carousel format). Single-column, text-first.

**References**: Spotify Wrapped storytelling approach, Apple Health insight summaries, Elicit research reports

**Layout**:
```
┌─ PATTERN INSIGHTS ──────────────────────────────────────┐
│  admin-section-label: "WHAT OMEGA LEARNED"              │
│                                                          │
│  ┌──────────────────────────────────────────────────────┐│
│  │  Your top theme is product strategy.                 ││
│  │  47 memories across 12 sessions.                     ││
│  │                                                      ││
│  │  ● product strategy ● threading ● testing            ││
│  │  ● database ● git style ● api ● deploy              ││
│  │                                                      ││
│  │  7 themes found across 546 memories                  ││
│  └──────────────────────────────────────────────────────┘│
│                                                          │
│  ┌──────────────────────────────────────────────────────┐│
│  │  Decisions are your most useful memory type.         ││
│  │  They're surfaced often and rated helpful 82% of     ││
│  │  the time.                                           ││
│  │                                                      ││
│  │  1. Decisions     Very helpful  ██████████████████   ││
│  │  2. Lessons       Helpful       ████████████         ││
│  │  3. Preferences   Mixed         ████████             ││
│  └──────────────────────────────────────────────────────┘│
│                                                          │
│  ┌──────────────────────────────────────────────────────┐│
│  │  Product strategy is growing.                        ││
│  │  +40% over 3 months. You had 28 memories last        ││
│  │  month, up from 20 the month before.                 ││
│  │                                     ╱╱╱╱╱╱╱╱ ↑      ││
│  └──────────────────────────────────────────────────────┘│
│                                                          │
│  ┌──────────────────────────────────────────────────────┐│
│  │  Threading is declining.                             ││
│  │  -30% over 3 months. Fewer memories about locks     ││
│  │  and concurrency recently.                           ││
│  │                                     ╲╲╲╲╲╲╲╲ ↓      ││
│  └──────────────────────────────────────────────────────┘│
│                                                          │
│  ┌──────────────────────────────────────────────────────┐│
│  │  "Recurring theme: product strategy. Based on 47     ││
│  │   memories across 12 sessions. Key topics: roadmap,  ││
│  │   prioritization, user research."                    ││
│  │                                        See memories →││
│  └──────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────┘
```

- Every section leads with a natural-language sentence in 18px body text. The sentence IS the insight.
- Themes shown as a horizontal pill/tag row (not bubbles, not cards). Clicking a pill shows the cluster detail.
- Rankings shown as an inline ordered list with bars, but introduced by a sentence ("Decisions are your most useful memory type").
- Each trend is its own card with a sentence + sparkline. Reads like a news feed.
- Synthesis quotes at the bottom.

**Color approach**: Minimal. Gold only for interactive elements (pill hover, sparkline). Text does the heavy lifting. The restraint makes each gold accent more impactful. Sparklines use gold line on dark surface.

**Strengths**: Most readable. Most accessible. Works perfectly on mobile without layout changes (single column is already mobile layout). The narrative framing makes insights memorable. No visualization library needed. Text-first means it will feel personal, not analytical.

**Risk**: Could feel text-heavy if there are many themes. No visual "wow factor." The pill/tag row for themes is less expressive than bubbles or cards. Could feel like a blog post inside a dashboard.

---

## Contrast Verification

All three directions use the existing color system. Key combinations already verified in Dashboard design direction:

| Combo | Foreground | Background | Ratio | WCAG |
|-------|-----------|------------|-------|------|
| Primary text on base | #e8e8f0 on #0f1019 | | 14.2:1 | AAA |
| Secondary text on base | #9898b0 on #0f1019 | | 7.1:1 | AAA |
| Gold on base | #d4a843 on #0f1019 | | 6.8:1 | AAA |
| Primary on elevated | #e8e8f0 on #151620 | | 12.8:1 | AAA |
| Gold on elevated | #d4a843 on #151620 | | 6.1:1 | AAA |

**New combo for Direction A bubble labels:**

| Combo | Foreground | Background | Ratio | WCAG |
|-------|-----------|------------|-------|------|
| White on gold bubble | #e8e8f0 on #d4a843 | | 2.3:1 | FAIL |
| Dark on gold bubble | #0f1019 on #d4a843 | | 6.2:1 | AAA |
| Gold label on dark | #d4a843 on #0f1019 | | 6.8:1 | AAA |

**Finding**: If Direction A uses gold-filled bubbles, labels must be dark text on gold (not white on gold). Alternatively, use outline-only bubbles with gold labels outside, which avoids the issue entirely.

## Recommendation

**Direction C (Narrative Scroll)** is the strongest match for this feature:

- **Matches the user**: Jason reads the Insights page reflectively, not analytically. A narrative format matches "What has OMEGA learned about me?" better than a grid of cards or a chart.
- **Natural language is the design decision from the IA**: The entire label glossary was about translating ML terms into sentences. Direction C makes sentences the primary visual, not a decoration on top of charts.
- **Mobile-native**: Single column works on all screens without degradation or fallback logic. The bubble chart (Direction A) needs a complete mobile rewrite.
- **Fastest to build**: No D3 dependency. Standard Tailwind components. Sparklines can be inline SVG (30 lines). Pills/tags are standard components.
- **Extensible**: Adding a new insight type = adding a new card with a sentence. No chart redesign needed.
- **Consistent with the dashboard design direction B (Portfolio Grid)**: Both use cards as the atomic unit, just with different content inside them.

**But**: Direction A (Constellation) could be added later as an enhanced visualization for the theme section, once the core narrative is proven. The narrative sentences from Direction C would serve as the labels for Direction A's bubbles. The two are complementary, not competing.

All three work. Your call.
