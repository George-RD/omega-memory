# Research Tab Redesign: Knowledge Curation + Plan Authoring

**Date**: 2026-03-15
**Status**: Approved

## Problem

The Research tab has a full autonomous experiment pipeline (scan, score, generate code diffs, dispatch to GitHub Actions, run pytest, create PRs). It's 2,000+ lines across 13 files, overengineered for the wrong job, and not being used.

The desired workflow: curate research knowledge and save implementation plans as markdown that can be recalled later by agents via `omega_query`.

## Design

### Layout: Two-column (replacing three-column)

**Left column: Research Library**
- Unified list of findings + plans
- Filter chips: All | High-priority | Scanner | Manual | Plans
- Each item shows: title, priority/status badge, subsystem pill, source icon, time ago
- Plans distinguished by a plan icon and status badge (draft/ready/implemented)

**Right column: Detail + Action Panel**
- **Finding selected**: full content, impact/feasibility/priority scores, source URL link, "Create Plan" button
- **Plan selected**: rendered markdown, status badge, linked finding reference, "Edit" button, metadata (subsystem, created date)
- **Plan editor mode**: markdown textarea with preview toggle, title field, status dropdown (draft/ready/implemented), save/cancel buttons. Finding context pre-populated as reference block when creating from a finding.

### Data Model

Plans stored in existing `memories` table (Supabase):
```
event_type: "research_plan"
content: <markdown plan text>
priority: 4
metadata: {
  status: "draft" | "ready" | "implemented",
  finding_id: <linked research_report memory id, nullable>,
  subsystem: <omega subsystem, nullable>,
  title: "Plan: <short descriptive title>"
}
```

Recalled by agents via `omega_query("plan for retrieval improvements", event_type="research_plan")`.

### API Changes

**`GET /api/admin/research`** - Add `source=plans` filter that returns `event_type = 'research_plan'` memories. Stats updated to include plan counts.

**`POST /api/admin/research`** - Add `type: "plan"` action to create/update plans. Payload: `{ type: "plan", title, content, status, subsystem, finding_id }`. Upserts to memories table.

**`DELETE /api/admin/research?id=<id>`** - Delete a plan by id (plans only, not findings).

**`POST /api/admin/research/scan`** - Keep scan functionality, remove experiment dispatch phases.

### Workflow

1. Scan or ingest research findings (unchanged)
2. Browse findings in the library, select one
3. Click "Create Plan" on a finding
4. Editor opens with finding content as a reference block at the top
5. Write implementation plan in markdown, set status to draft
6. Save - plan appears in library with plan icon
7. Later: update status to "ready" when plan is refined, "implemented" when done
8. Agents recall plans via omega_query

### Files to Delete

| File | Lines | Purpose (removed) |
|------|-------|--------------------|
| `lib/research-experiment.ts` | 792 | Experiment generation, code diffs, GitHub dispatch |
| `lib/research-pipeline.ts` | 180 | Autonomous scan-to-experiment loop |
| `app/api/admin/research/experiment/route.ts` | ~200 | Experiment CRUD + run/accept/reject |
| `components/research/ExperimentPipeline.tsx` | ~200 | Experiment list + action buttons UI |

**Total removed**: ~1,370 lines

### Files to Modify

| File | Changes |
|------|---------|
| `Research.tsx` | Two-column layout, remove experiment state/fetching, add plan state, plan creation flow |
| `FindingDetail.tsx` | Remove experiment status/buttons, add "Create Plan" button |
| `FindingsList.tsx` | Add Plans filter chip, render plans with distinct icon/badge |
| `app/api/admin/research/route.ts` | Add plan CRUD (create, update, delete), plans filter in GET |
| `app/api/admin/research/scan/route.ts` | Remove experiment dispatch phases, keep scan only |
| `components/research/helpers.ts` | Add plan-related constants (status colors, icons) |
| `components/research/types.ts` | Add ResearchPlan type, update ResearchData |

### Files to Create

| File | Purpose |
|------|---------|
| `components/research/PlanEditor.tsx` | Markdown editor with preview toggle, title/status fields, save/cancel |
| `components/research/PlanDetail.tsx` | Rendered markdown plan view with edit button, status badge, metadata |

### UX Details

- **Plan editor**: Simple markdown textarea (no WYSIWYG). Preview toggle shows rendered markdown. Title field at top, status dropdown, subsystem dropdown (optional). Save and Cancel buttons at bottom.
- **Plan status badges**: Draft (gray), Ready (green), Implemented (blue) - consistent with existing badge patterns.
- **Create Plan from finding**: Pre-populates a blockquote reference of the finding content at the top of the plan, with the finding's technique as the title prefix.
- **Empty state**: When no plans exist, show a helpful message: "Select a research finding and click 'Create Plan' to start."
- **Plan icon**: Use a document/clipboard icon to distinguish from research finding icons (source-based).
