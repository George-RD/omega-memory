# OMEGA Memory — Security Fork

This is George's security fork of [omega-memory](https://github.com/omega-memory/omega-memory).

## What This Fork Adds

All fork-only changes live on the `fork/security` branch:

- **`scripts/secure_model_download.py`** — Downloads ONNX model with SHA256 hash verification,
  size bounds checking, and ONNX header validation. Hashes are pinned from a verified download.
- **`scripts/omega_boot_check.py`** — Pre-flight check: verifies package, database, model,
  file permissions, and confirms no Claude Code hooks are installed.
- **`scripts/check_upstream_before_sync.sh`** — 7-check security audit to run before merging
  upstream changes (network calls, subprocess/exec, telemetry, hooks, deps, model URLs, bandit).
- **`.gitignore` additions** — Fork-specific entries for runtime data, model cache, security artifacts.
- **`pyproject.toml`** — Relaxed `requires-python` from `>=3.11` to `>=3.10` (no 3.11 syntax used).

## Key Commands
```bash
# Sync upstream (ALWAYS audit first)
bash scripts/check_upstream_before_sync.sh
git fetch upstream && git merge upstream/main

# Verify model integrity
python3 scripts/secure_model_download.py --check-only

# Full health check
python3 scripts/omega_boot_check.py

# Static security scan
bandit -r src/ -ll --quiet
```

## Security Audit Summary (v0.10.0)

- **No telemetry, no phone-home, no data exfiltration** — all storage is local SQLite
- **Hook system** sees all prompts/tool outputs (medium risk, by design)
- **Plugin system** has no sandboxing (critical risk, but we don't use plugins)
- **SQL injection flags** were all false positives (parameterized queries throughout)
- **No network calls** outside optional model download

## Branch Workflow

- Fork-only changes: commit to `fork/security`, merge into `main`
- Upstream PRs: branch from `main` after syncing upstream, never include fork/security
- Before merging upstream: always run `check_upstream_before_sync.sh`
- Full details: see FORK_MAINTENANCE.md
