# Wireframes: OMEGA Admin Dashboard (Dashboard Tab)

Direction: Portfolio Grid (B)

## Desktop Layout (>= 1024px)

```
┌─────────────────────────────────────────────────────────────────────┐
│  SYSTEM HEALTH BAR                                                  │
│  ● OMEGA  ● Jobs (5/5)  ● Cloud  ● Website  ● X API    [Refresh]  │
│  All systems healthy                                     2m ago     │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  💡 Suggestions                                                     │
│  • PyPI downloads flat this week. Consider a dev.to post.     →     │
│  • memorystress has 0 GitHub stars. Share on X.               →     │
│  • Engagement rate up 1.2% — thread format is working.        →     │
└─────────────────────────────────────────────────────────────────────┘

┌─ PROJECT CARDS (3-col grid, draggable, pinnable) ──────────────────┐
│                                                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐    │
│  │ 📌 OMEGA         │  │ kokyo            │  │ app-o-matic      │    │
│  │ Open Source      │  │ Foundation       │  │ SaaS             │    │
│  │                  │  │                  │  │                  │    │
│  │ ⭐ 42 stars      │  │ 3 in pipeline    │  │ v1.4.3           │    │
│  │ 📦 1.2K dl/mo    │  │ 1 submitted      │  │ 0 users          │    │
│  │ 🍴 8 forks       │  │ €0 won           │  │ $0 MRR           │    │
│  │                  │  │                  │  │                  │    │
│  │ v0.10.2 on PyPI  │  │ Next: qualify    │  │ Last deploy:     │    │
│  │ 3 commits/wk     │  │ 2 grants         │  │ 14d ago          │    │
│  │                  │  │                  │  │                  │    │
│  │ ████████░░ 80%   │  │ ██░░░░░░░░ 20%   │  │ ██████░░░░ 60%   │    │
│  │ Growing          │  │ Pre-launch       │  │ Paused           │    │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘    │
│                                                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐    │
│  │ memorystress     │  │ jason-sosa.com   │  │ orchestrator     │    │
│  │ Benchmark        │  │ Portfolio        │  │ Tool             │    │
│  │                  │  │                  │  │                  │    │
│  │ 📦 0 dl/mo       │  │ Last deploy:     │  │ Last commit:     │    │
│  │ HF: 12 views     │  │ 7d ago           │  │ 30d ago          │    │
│  │ ⭐ 0 stars       │  │ ● Live           │  │ No releases      │    │
│  │                  │  │                  │  │                  │    │
│  │ Published        │  │ ● Live           │  │ Backlog          │    │
│  │ PyPI + HF + GH   │  │                  │  │                  │    │
│  │                  │  │                  │  │                  │    │
│  │ ██████████ Done   │  │ ██████████ Live  │  │ █░░░░░░░░░ 10%   │    │
│  │ Launched         │  │ Live             │  │ Backlog          │    │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘    │
│                                                                     │
│  ┌─────────────────┐  ┌─────────────────┐                          │
│  │ polymarket       │  │ OMEGA Website    │                          │
│  │ Trading          │  │ Marketing        │                          │
│  │                  │  │                  │                          │
│  │ P&L: +$0         │  │ omegamax.co      │                          │
│  │ 0 positions      │  │ Last deploy:     │                          │
│  │                  │  │ today            │                          │
│  │                  │  │ ● Live           │                          │
│  │                  │  │                  │                          │
│  │ █░░░░░░░░░ 10%   │  │ ██████████ Live  │                          │
│  │ Pre-launch       │  │ Live             │                          │
│  └─────────────────┘  └─────────────────┘                          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Project Card Detail (expanded on click)

```
┌─────────────────────────────────────────────────────────────────────┐
│ 📌 OMEGA                                              Open Source   │
│ Persistent memory for AI agents                        [Unpin] [↗]  │
│─────────────────────────────────────────────────────────────────────│
│                                                                     │
│  Metrics                          Shipping                          │
│  ⭐ 42 stars (+3 this week)       v1.0.0 (private)                  │
│  📦 1,247 downloads/mo (+12%)     v0.10.2 (PyPI public)             │
│  🍴 8 forks (19% fork rate)       3 commits this week               │
│  👥 1 contributor                 Last release: 3d ago              │
│                                   0 open PRs                        │
│                                                                     │
│  ROI                              Launch Readiness                  │
│  Primary value: Strategic         ████████░░ 80%                    │
│  Downloads growing 12%/mo         ✓ PyPI published                  │
│  Engagement: 4.2% avg             ✓ Docs live                       │
│                                   ✓ Benchmarks published            │
│                                   ○ 100 stars (for pro reveal)      │
│                                   ○ Community growth                │
│                                                                     │
│  ⚡ Suggestion                                                      │
│  Downloads up but stars flat. Try a Reddit /r/MachineLearning post. │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Mobile Layout (< 1024px)

```
┌───────────────────────────────┐
│  SYSTEM HEALTH                │
│  ● All healthy     [Refresh]  │
│  5/5 jobs · cloud ok · 2m     │
└───────────────────────────────┘

┌───────────────────────────────┐
│  💡 Downloads flat. Post →     │
│     Stars: 0 on memstress →    │
└───────────────────────────────┘

┌───────────────────────────────┐
│ 📌 OMEGA          Open Source │
│ ⭐ 42   📦 1.2K   🍴 8       │
│ ████████░░ Growing            │
└───────────────────────────────┘

┌───────────────────────────────┐
│ kokyo             Foundation  │
│ 3 pipeline   1 submitted      │
│ ██░░░░░░░░ Pre-launch         │
└───────────────────────────────┘

┌───────────────────────────────┐
│ app-o-matic            SaaS  │
│ v1.4.3   $0 MRR               │
│ ██████░░░░ Paused             │
└───────────────────────────────┘

(... more cards, single column)

┌───────────────────────────────┐
│  [Dashboard] [Feed] [Actions] │
│  [Insights]  [More]           │
└───────────────────────────────┘
```

## System Health Bar States

```
Normal (all green):
┌─────────────────────────────────────────────────────────────────┐
│  ● OMEGA  ● Jobs (5/5)  ● Cloud  ● Website  ● X API   2m ago  │
└─────────────────────────────────────────────────────────────────┘

Issue detected (expands):
┌─────────────────────────────────────────────────────────────────┐
│  ● OMEGA  ⚠ Jobs (3/5)  ● Cloud  ● Website  ● X API   2m ago  │
│─────────────────────────────────────────────────────────────────│
│  ✕ daily-digest: failed 2h ago — "SMTP timeout"          [→]   │
│  ✕ tweet-scanner: failed 45m ago — "Rate limit"          [→]   │
└─────────────────────────────────────────────────────────────────┘
```

## Layout Decisions

| Decision | Choice | Reasoning |
|----------|--------|-----------|
| Grid columns | 3 desktop, 2 tablet, 1 mobile | 8 projects fit comfortably in 3 cols without scrolling |
| Health bar position | Fixed at top of scroll area | Always visible, answers #1 question immediately |
| Suggestions placement | Between health and cards | Seen every visit but doesn't dominate |
| Card height | Variable (content-driven) | Cards with more metrics are taller, that's fine |
| Expanded card | Replaces card in-place, pushes grid down | No modal/overlay needed for single-user tool |
| Pin indicator | Gold left border (existing admin-card pattern) | Consistent with existing design language |
| Category tint | Subtle bg tint on card (5% opacity semantic color) | Blue=OSS, green=SaaS, amber=foundation, etc. |

## Responsive Strategy

| Breakpoint | Layout | Changes |
|-----------|--------|---------|
| >= 1280px | 3-col grid, full health bar | Full experience |
| 1024-1279px | 2-col grid, full health bar | Cards wrap to 2 cols |
| 768-1023px | 2-col grid, compact health | Health bar stacks to 2 lines |
| < 768px | 1-col grid, minimal health | Single column, health collapses to summary |

## Component Inventory

| Component | Complexity | Lines (est) |
|-----------|-----------|-------------|
| SystemHealthBar | Medium | ~120 |
| SuggestionsPanel | Simple | ~60 |
| ProjectCard (collapsed) | Medium | ~100 |
| ProjectCard (expanded) | Medium | ~150 |
| ProjectGrid (container + drag) | Medium | ~80 |
| CategoryPill | Simple | ~20 |
| LaunchProgressBar | Simple | ~30 |
| Dashboard (orchestrator) | Medium | ~100 |
| **Total** | | **~660** |

Note: current Dashboard.tsx is 715 lines as a monolith. New version splits into 8 focused components, largest ~150 lines.

## Build Sequence

1. **SystemHealthBar** — answers the #1 question, no dependencies
2. **ProjectCard (collapsed)** + **CategoryPill** + **LaunchProgressBar** — the core visual unit
3. **ProjectGrid** — container with drag-to-reorder
4. **SuggestionsPanel** — simple list, no dependencies
5. **ProjectCard (expanded)** — detail view, builds on collapsed card
6. **Dashboard** — orchestrator that wires everything together
