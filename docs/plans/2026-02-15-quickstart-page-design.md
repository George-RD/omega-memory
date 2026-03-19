# Quickstart Page Design

**Date**: 2026-02-15
**Trigger**: Reddit comment asking how auto-capture works and requesting architecture details

## Goal

Build `/quickstart` page on omegamax.co that explains OMEGA's architecture (MCP server, hooks, no background AI), then walks through install/setup. Target: developers evaluating the tool.

## Approach

Linear walkthrough (Approach A). Architecture-first, install second. Claude Code as primary client. Diagram + prose for auto-capture explanation.

## Sections

### 1. Hero
- Section label: "Quick Start"
- Heading: "From Zero to **Persistent Memory** in 2 Minutes"
- Subtitle clarifying OMEGA is an MCP server, not a background AI

### 2. Architecture (How It Works)
- 4-node flow diagram: MCP Client <-> MCP Protocol <-> OMEGA Server -> SQLite + Vectors
- 3 cards: "No background AI", "Hooks not surveillance", "Local-first storage"

### 3. Auto-Capture Loop
- 4-step lifecycle: session starts -> protocol loads -> during work -> session ends
- Prose explaining hooks + protocol instructions = "auto"

### 4. Install (3 Steps)
- Step 1: `pip install omega-memory`
- Step 2: `omega setup`
- Step 3: `omega doctor`
- Link to /docs for other clients (Cursor, Windsurf, Zed)

### 5. Try It
- Terminal showing first memory interaction (welcome, store preference, next session retrieval)

### 6. Bottom CTA
- OmegaMark + "Ready to Remember?"
- Buttons: "Read the Docs" + "View on GitHub"

## Additional Fix
- Update /how-it-works to show 12 MCP tools (currently says 27, outdated)

## Components Used
- ScrollReveal, Terminal, OmegaMark
- Styled divs for architecture diagram (matching existing pattern on /how-it-works)
- Standard card, section-label, gold-gradient-text, btn-primary/btn-secondary
