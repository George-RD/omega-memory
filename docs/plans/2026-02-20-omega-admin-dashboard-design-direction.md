# Design Direction: OMEGA Admin Dashboard (Dashboard Tab)

## Existing Brand (keep)

- **Fonts**: Outfit (display/body), JetBrains Mono (data/labels)
- **Base surface**: #0f1019 (dark), elevated #151620, hover #1c1d2a
- **Ink**: #e8e8f0 (primary), #9898b0 (secondary), #686880 (tertiary)
- **Accent**: Gold #d4a843 (dim #b89035, muted #7a6838)
- **Semantic**: Decision blue #6b9fff, Lesson green #5ec9a0, Error red #f06060, Reminder amber #e8a040

Not proposing a rebrand. The design system is solid. The problem is layout, information hierarchy, and font sizes.

## Typography System (enforced minimums)

| Element | Current | Proposed | Minimum |
|---------|---------|----------|---------|
| Body text | 13px | 18px | 18px |
| Secondary text | 14px | 16px | 16px |
| Labels/captions | 11px | 15px | 14px |
| Section labels (mono) | 11px | 14px | 14px |
| Metric values | 32px | 36px | 32px |
| Page heading | 20px | 28px | 24px |
| Card headings | N/A | 20px | 18px |
| Line height | ~1.3 | 1.6 | 1.5 |

## Three Directions

---

### Direction A: Status Board

**Feeling**: Calm confidence. Like a pilot's instrument panel where green means "keep flying."

**References**: Better Stack status pages, Apple Health summary, iOS Weather app

**Layout**:
- System health as a large, dominant **status strip** across the top. All-green = one calm line. Any issue = expands with details.
- Below: project cards in a **2-column grid** (desktop), 1-column (mobile)
- Each card is a compact rectangle: project name, category pill, 2-3 key metrics, mini progress bar for launch readiness
- "What can be improved" as a subtle section at the bottom, styled like quiet suggestions
- Cards are draggable to reorder (focus priority)

**Color approach**: Primarily monochrome (ink on surface). Gold only for interactive elements. Semantic colors only for status indicators. The calmness comes from restraint.

**Strengths**: Clean, scannable, doesn't demand attention when things are fine. Feels premium.
**Risk**: Could feel too minimal for a command center with 8 projects.

---

### Direction B: Portfolio Grid

**Feeling**: Like opening your investment portfolio. Each project is an asset you're tracking.

**References**: Railway project dashboard, Vercel project list, Linear project views

**Layout**:
- Compact system health bar at top (single row of indicators)
- Project cards as **larger, richer cards** in a responsive grid (3 columns desktop, 2 tablet, 1 mobile)
- Each card has: project name + category tag, sparkline or mini chart for primary metric, key numbers, launch progress as a segmented bar (Phase 1/2/3/4/5 or pre-launch/alpha/beta/live), last activity timestamp
- Cards are pinnable: pinned cards get a gold border accent and sort to top
- "Improvements" section integrated as callout badges on relevant project cards (e.g., a small amber badge "Downloads flat" on the memorystress card)

**Color approach**: More color than A. Each project category gets a subtle tint on its card (open source = blue tint, SaaS = green tint, foundation = amber tint). Gold for pinned/focused.

**Strengths**: Rich, informative, each project feels like a first-class citizen. The category tinting makes scanning by project type fast.
**Risk**: More visual complexity. Could feel busy with 8 cards.

---

### Direction C: Mission Control Rows

**Feeling**: Dense but scannable, like a flight controller's display. Every row is a system.

**References**: Linear's list view, Datadog service catalog, GitHub repository list

**Layout**:
- System health as a **prominent header block**: large green/amber/red indicator with summary text ("All systems healthy" or "2 issues"). Takes up real estate when there's a problem, collapses to one line when clean.
- Projects as **full-width rows** (not cards), each row contains: drag handle, project name, category pill, 3-4 inline metrics, launch status badge, sparkline
- Rows expand on click to show detailed metrics, recent commits, ROI breakdown
- "Improvements" as an inline section between health and projects: 3 one-liner suggestions with arrow links
- Rows are reorderable via drag

**Color approach**: Minimal. Row backgrounds alternate subtly. Gold for the focused/pinned row. Semantic colors for status badges only.

**Strengths**: Most information-dense. Scales well from 3 to 15 projects. Feels like a command line for people who like density.
**Risk**: Less visual interest. Could feel like a spreadsheet if not carefully styled.

---

## Contrast Verification

All directions use the existing color system. Key combinations:

| Combo | Foreground | Background | Ratio | WCAG |
|-------|-----------|------------|-------|------|
| Primary text on base | #e8e8f0 on #0f1019 | | 14.2:1 | AAA |
| Secondary text on base | #9898b0 on #0f1019 | | 7.1:1 | AAA |
| Tertiary text on base | #686880 on #0f1019 | | 3.8:1 | AA Large only |
| Faint text on base | #404058 on #0f1019 | | 2.1:1 | FAIL |
| Gold on base | #d4a843 on #0f1019 | | 6.8:1 | AAA |
| Primary on elevated | #e8e8f0 on #151620 | | 12.8:1 | AAA |

**Issue**: `text-ink-faint` (#404058) fails contrast at 2.1:1. At 18px+ body text this becomes less critical (AA Large requires 3:1), but it should only be used for decorative/non-essential elements, never for content the user needs to read.

**Fix for new design**: Replace `ink-faint` usage in readable text with `ink-tertiary` (#686880, 3.8:1) minimum. Reserve `ink-faint` for borders and decorative elements only.

## Recommendation

**Direction B (Portfolio Grid)** is the strongest match for the IA:
- Project cards as the hero content maps directly to "cards represent what my focus is"
- Pinning + reordering gives you control over focus
- Category tinting makes visual scanning fast
- Rich enough to feel like a command center, not a bare status page
- Improvement badges on cards keep suggestions contextual rather than a separate section

But all three work. Your call.
