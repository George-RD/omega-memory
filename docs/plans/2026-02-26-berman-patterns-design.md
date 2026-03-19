# Berman-Inspired Systems Design

**Date**: 2026-02-26
**Source**: Matthew Berman's "5 Billion Tokens" OpenClaw video + shared prompts/MD files
**Scope**: OMEGA, polymarket-omega, Conductor

---

## 1. Notification Batching in OMEGA Coordination

**Project**: OMEGA (private) at `~/Projects/omega/`
**Files**: `src/omega/coordination.py`, `src/omega/coord_handlers.py`

### Schema Change

Add 3 columns to `coord_messages` (v11 migration):

```sql
ALTER TABLE coord_messages ADD COLUMN priority TEXT DEFAULT 'medium';
-- Values: 'critical' | 'high' | 'medium'

ALTER TABLE coord_messages ADD COLUMN batch_id TEXT;
-- Groups messages delivered in the same flush digest

ALTER TABLE coord_messages ADD COLUMN delivered_at TEXT;
-- NULL until message is flushed/delivered. Critical messages get delivered_at = created_at immediately.
```

Add index:
```sql
CREATE INDEX idx_coord_messages_pending ON coord_messages(priority, delivered_at) WHERE delivered_at IS NULL;
```

### Handler Changes

**`omega_send_message`** (coord_handlers.py):
- Add optional `priority` parameter (default: 'medium')
- If priority = 'critical': set `delivered_at = now()`, call `notify_session()` immediately (current behavior)
- If priority = 'high' or 'medium': insert with `delivered_at = NULL`, skip `notify_session()`

**`omega_inbox`** (coordination.py):
- Continue returning messages where `delivered_at IS NOT NULL` OR `priority = 'critical'`
- Add a `include_pending` boolean param for agents that want to peek at queued messages

**New: `flush_notification_batch()`** (coordination.py):
- Called by maintenance cycle
- Query: `WHERE delivered_at IS NULL AND priority = ? AND created_at < cutoff`
- Cutoff: 1 hour ago for 'high', 3 hours ago for 'medium'
- Group by `to_session` (or `project` for broadcasts)
- Set `batch_id` to a shared UUID for grouped messages
- Set `delivered_at = now()`
- Call `notify_session()` for each recipient with a digest summary

### Backwards Compatibility

- Default priority = 'medium' means existing code continues working
- `delivered_at` is set immediately for critical messages, so `omega_inbox` returns them instantly
- Agents unaware of batching see no behavior change (they'll just get messages slightly delayed)

---

## 2. Signal Scoring Rubric for polymarket-omega

**Project**: polymarket-omega at `~/Projects/polymarket-omega/`
**Files**: New `config/signal_rubric.md`, modified `agents/probability_estimator.py`

### Rubric File: `config/signal_rubric.md`

Markdown file read by the probability estimator as part of the prompt context. Editable without code changes.

```markdown
# Signal Scoring Rubric

## Dimensions (weighted)

| Dimension | Weight | Description |
|-----------|--------|-------------|
| Source Credibility | 25% | Historical accuracy of this data source. SoSoValue ETF = high. Unknown Twitter account = low. |
| Signal Magnitude | 20% | Size of deviation from baseline. 3-sigma move = exceptional. 0.5-sigma = noise. |
| Time Sensitivity | 20% | Freshness relative to signal half-life. Within 1 half-life = full weight. Beyond 3 = near-zero. |
| Corroboration | 20% | How many independent sources confirm this direction. 3+ = exceptional. 0 = low. |
| Novelty | 15% | Is this genuinely new information or restating known facts. First report = high. 5th article on same news = low. |

## Score Buckets

| Bucket | Score | Action |
|--------|-------|--------|
| Exceptional | 80-100 | Immediate alert. Boost ensemble weight by 1.5x. |
| High | 60-79 | Include in daily digest with emphasis. Standard ensemble weight. |
| Medium | 40-59 | Standard processing. No special treatment. |
| Low | 20-39 | Downweight in ensemble by 0.5x. Log only. |
| Noise | 0-19 | Skip entirely. Log reason for exclusion. |

## Source Credibility Baselines

| Source | Default Credibility | Notes |
|--------|-------------------|-------|
| SoSoValue (ETF flows) | 85 | Primary, verified against CoinGlass |
| CoinMetrics (MVRV, hashrate) | 80 | Academic-grade, well-maintained |
| BGeometrics (Puell, SOPR) | 70 | Free tier, rate-limited |
| Mempool.space (price, fees) | 75 | Open-source, live data |
| BLS (macro) | 90 | Government data, high reliability |
| Sharpe AI (mindshare) | 55 | Newer source, validate against outcomes |
| Kaito Yaps (social) | 50 | Social signal, inherently noisy |
| Polymarket orderbook (VPIN) | 65 | Derived signal, depends on liquidity |
```

### Implementation

**New file**: `libs/signal_scorer.py`

```python
class SignalScorer:
    def __init__(self, rubric_path: str = "config/signal_rubric.md"):
        self.rubric = self._load_rubric(rubric_path)

    def score_signal(self, signal: dict) -> dict:
        """Score a single signal against the rubric.
        Returns: {score: int, bucket: str, breakdown: dict, action: str}
        """

    def score_batch(self, signals: list[dict]) -> list[dict]:
        """Score all signals for a day. Returns sorted by score descending."""

    def apply_feedback(self, signal_id: str, actual_outcome: str, rubric_path: str):
        """After market resolution, update source credibility baselines."""
```

**Integration**: `agents/probability_estimator.py` calls `SignalScorer.score_batch()` before constructing the ensemble prompt. Scored signals include their score in the prompt context so Claude can weight them accordingly. The rubric markdown is included in the system prompt.

**Output**: `data/signal_scores_YYYY-MM-DD.json` alongside existing data files.

**Feedback loop**: `agents/calibrator.py` (weekly, Sundays) compares signal scores vs. actual market outcomes. Updates source credibility baselines in rubric.

---

## 3. Cron Infrastructure for Conductor

**Project**: Conductor at `~/Projects/conductor/`
**Files**: New `src/conductor/engine/cron_manager.py`, schema additions to `conductor.db`

### Schema (new tables in conductor.db)

```sql
CREATE TABLE cron_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',  -- running | success | failure
    summary TEXT,
    duration_seconds REAL,
    error_detail TEXT
);

CREATE INDEX idx_cron_runs_job ON cron_runs(job_name, started_at DESC);
CREATE INDEX idx_cron_runs_status ON cron_runs(status) WHERE status = 'running';

CREATE TABLE cron_locks (
    job_name TEXT PRIMARY KEY,
    pid INTEGER NOT NULL,
    acquired_at TEXT NOT NULL,
    hostname TEXT
);
```

### CronManager Module

```python
class CronManager:
    def __init__(self, db_path: str = "conductor.db"):
        self.db_path = db_path

    def log_start(self, job_name: str) -> int:
        """Insert running row, return run_id."""

    def log_end(self, run_id: int, status: str, summary: str = ""):
        """Update completed_at, status, duration_seconds."""

    def should_run(self, job_name: str, interval: str) -> bool:
        """Idempotency: skip if already succeeded within interval.
        interval: '1h', '1d', '1w'
        """

    def acquire_lock(self, job_name: str) -> bool:
        """PID-based lock. Check if existing lock's PID is alive.
        If dead PID, steal the lock. If alive, return False.
        """

    def release_lock(self, job_name: str):
        """Remove lock row."""

    def cleanup_stale(self, max_age_hours: int = 2):
        """Mark jobs stuck in 'running' for >max_age_hours as 'failure'.
        Called on every new job start.
        """

    def detect_persistent_failures(self, job_name: str,
                                    window_hours: int = 6,
                                    threshold: int = 3) -> bool:
        """Return True if job failed >= threshold times in window.
        Integrates with Conductor's circuit_breaker.py.
        """

    def get_history(self, job_name: str = None, status: str = None,
                    days: int = 7) -> list[dict]:
        """Query cron history with filters."""
```

### Integration with Existing Conductor Components

- **`circuit_breaker.py`**: When `detect_persistent_failures()` returns True, open the circuit for that job
- **`dead_letter.py`**: Failed cron jobs with error details go to DLQ for retry
- **`supervisor.py`**: Supervisor monitors cron health alongside workflow health
- **`notification_router.py`**: Alert on persistent failures via existing notification system

### Context Manager for Job Execution

```python
@contextmanager
def cron_job(self, job_name: str, interval: str = None):
    """Usage:
    with cron_manager.cron_job("daily_pipeline", interval="1d") as run:
        if run.skipped: return  # already ran today
        do_work()
    # auto logs success/failure, releases lock
    """
```

---

## 4. LLM Usage Tracking in OMEGA

**Project**: OMEGA (private) at `~/Projects/omega/`
**Files**: `src/omega/coordination.py` (schema), new `src/omega/usage_tracker.py`, `website/app/admin/`

### Schema (new table in coordination DB, v11 migration)

```sql
CREATE TABLE llm_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    tool_name TEXT NOT NULL,
    model TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'anthropic',
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_write_tokens INTEGER DEFAULT 0,
    estimated_cost_usd REAL DEFAULT 0.0,
    duration_ms INTEGER,
    project TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_llm_usage_session ON llm_usage(session_id);
CREATE INDEX idx_llm_usage_tool ON llm_usage(tool_name, created_at);
CREATE INDEX idx_llm_usage_created ON llm_usage(created_at);
```

### Usage Tracker Module

```python
# src/omega/usage_tracker.py

MODEL_PRICING = {  # per 1M tokens (USD)
    "claude-opus-4-6":   {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_write": 18.75},
    "claude-sonnet-4-6": {"input": 3.0,  "output": 15.0, "cache_read": 0.3, "cache_write": 3.75},
    "claude-haiku-4-5":  {"input": 0.8,  "output": 4.0,  "cache_read": 0.08, "cache_write": 1.0},
    "nomic-embed-text":  {"input": 0.0,  "output": 0.0},  # local
}

class UsageTracker:
    def log_call(self, session_id, tool_name, model, input_tokens, output_tokens,
                 cache_read=0, cache_write=0, duration_ms=None, project=None):
        """Fire-and-forget logging. Computes estimated_cost from MODEL_PRICING."""

    def get_usage(self, days=7, group_by="model") -> list[dict]:
        """Aggregated usage: by model, by tool, by session, by day."""

    def get_cost_estimate(self, days=30) -> dict:
        """Total estimated cost with breakdown."""

    def get_top_tools(self, days=7, limit=10) -> list[dict]:
        """Tools ranked by token consumption."""
```

### Integration Points

1. **Bridge layer** (`bridge.py`): After every embedding call, log to usage tracker (model="nomic-embed-text", cost=0)
2. **MCP server**: Wrap tool handlers to capture token counts from Claude's response metadata when available
3. **Coordination handlers**: Log coord_audit calls that trigger LLM usage

### Admin Dashboard Widget

New component on the existing "Dashboard" tab:

- **Daily token usage** line chart (7-day, 30-day toggle)
- **Cost estimate** card (current month)
- **Top tools by tokens** bar chart
- **Model distribution** pie chart (Opus vs Sonnet vs Haiku vs local)

API route: `GET /api/admin/llm-usage?days=7&group_by=model`

---

## 5. Nightly Self-Audit Council

**Project**: OMEGA (cross-project tool)
**Files**: New `src/omega/council.py`, new MCP tool `omega_council`, per-project configs

### New MCP Tool: `omega_council`

```python
omega_council(
    domain: str,        # "platform_health" | "security" | "innovation"
    project: str = None # scope to specific project, or None for all
) -> dict
```

### Three Council Domains

**Platform Health** (nightly):
- Query OMEGA for recent errors (event_type="error_pattern", last 24h)
- Query coord_audit for tool failure rates
- Query cron_runs (Conductor) for reliability stats
- Check memory store health metrics
- Produce: severity-ranked issues, health score 0-100

**Security** (nightly):
- Scan for credential-looking strings in recent memories
- Check for prompt injection patterns in stored content
- Review external action audit trail
- Check file permissions on sensitive configs
- Produce: vulnerability report, risk score

**Innovation Scout** (weekly):
- Query OMEGA for all current capabilities (tools, entities, decisions)
- Search web for new AI agent use cases and patterns
- Compare capabilities vs. community patterns
- Produce: ranked feature proposals with effort estimates

### Per-Project Config

Store in each project's config directory as markdown:

```
~/Projects/omega/config/councils/platform_health.md
~/Projects/omega/config/councils/security.md
~/Projects/omega/config/councils/innovation.md
~/Projects/polymarket-omega/config/councils/platform_health.md
~/Projects/conductor/config/councils/platform_health.md
```

Each file is a system prompt template for that council + project combination.

### Storage & Feedback

- Findings stored as OMEGA memories: `event_type="council_finding"`, tagged with domain + project
- User responds "accept" or "reject" per finding
- Accepted → stored as `event_type="decision"`
- Rejected → stored as `event_type="lesson_learned"` with rejection reason
- Future councils query past findings to avoid repeating rejected suggestions

### Delivery

- Post digest to appropriate channel (Telegram topic, Slack, etc.)
- Priority: Critical findings = immediate, others = batched (uses system #1)
- Weekly summary comparing health scores over time

---

## Cross-Cutting Concerns

### Schema Migration Strategy

OMEGA coordination DB needs v11 migration adding:
- `coord_messages`: priority, batch_id, delivered_at columns
- `llm_usage`: new table
- Run via existing migration pattern in `coordination.py`

### No Breaking Changes

All 5 systems are additive. No existing behavior changes unless agents opt in by specifying priority or using new tools.
