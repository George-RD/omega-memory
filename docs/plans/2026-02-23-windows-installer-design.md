# OMEGA Windows Installer Design

**Date**: 2026-02-23
**Status**: Approved
**Goal**: One-click installer for non-technical Claude Desktop users on Windows

## Target User

Claude Desktop users who are comfortable with Claude but not developers. May not have Python installed. Expect a standard Windows installer experience.

## Architecture

```
omega-setup.exe (Inno Setup, ~180MB)
+-- Embedded Python 3.12 (embeddable package, ~20MB)
+-- Pre-built venv with omega-memory[server] + all deps (~150MB)
+-- Post-install script:
|   +-- Run `omega setup` (downloads ONNX model ~90MB on first run)
|   +-- Find Claude Desktop config at %APPDATA%\Claude\claude_desktop_config.json
|   +-- Backup existing config
|   +-- Inject OMEGA MCP server entry
+-- Uninstaller (removes venv, reverts Claude Desktop config)
```

## User Experience

1. Download `omega-setup.exe` from omegamax.co or GitHub releases
2. Run installer: standard "Next > Next > Install" wizard
3. Wait: installs Python venv + OMEGA, downloads embedding model, configures Claude Desktop
4. Restart Claude Desktop: OMEGA tools are now available
5. Say "hello" to Claude: `omega_welcome` works immediately

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Python | Bundled embeddable 3.12 | No PATH conflicts, guaranteed compatibility |
| Installer | Inno Setup | Free, professional, familiar UX |
| Install location | `%LOCALAPPDATA%\OMEGA\` | Standard per-user app location |
| Data location | `%USERPROFILE%\.omega\` | Matches macOS `~/.omega/` |
| Claude config | Auto-configure with backup | Minimal friction |
| Hook socket | TCP `127.0.0.1:19876` on Windows | Unix sockets unavailable |
| Embedding daemon | In-process loading | Skip Unix socket daemon on Windows |
| Admin privileges | Not required | Per-user install only |

## Windows Compatibility Fixes Required

These changes must be made to the OMEGA Python codebase before the installer can work:

### 1. Hook Server: TCP Socket Fallback
- **File**: `src/omega/server/hook_server/__init__.py`
- **Change**: When `os.name == 'nt'`, use TCP socket `127.0.0.1:19876` instead of Unix domain socket `~/.omega/hook.sock`
- **Impact**: Hook dispatch works identically, just different transport

### 2. Embedding Daemon: In-Process Fallback
- **File**: `src/omega/embedding_daemon.py`
- **Change**: When `os.name == 'nt'`, skip Unix socket daemon, load ONNX model in-process
- **Impact**: Slightly higher memory per Claude Desktop instance, but functional

### 3. Path Handling Verification
- **Files**: Various, especially `sqlite_store.py`
- **Change**: Verify `Path.home()` resolves correctly on Windows, ensure no hardcoded `/` separators
- **Impact**: Data directory creation and access

### 4. CI: Windows Runner
- **File**: `.github/workflows/ci.yml`
- **Change**: Add `windows-latest` to test matrix
- **Impact**: Catches regressions on Windows going forward

## Installer Components

### Inno Setup Script (`installer/omega-setup.iss`)
- Defines install wizard pages, file locations, post-install actions
- Runs `omega setup` as post-install step
- Configures Claude Desktop's MCP config

### Post-Install Script (`installer/configure.py`)
- Reads `%APPDATA%\Claude\claude_desktop_config.json`
- Backs up to `claude_desktop_config.json.bak`
- Merges OMEGA MCP server entry into `mcpServers` key
- Handles case where config file or `mcpServers` key doesn't exist yet

### Uninstaller Behavior
- Removes `%LOCALAPPDATA%\OMEGA\` (venv + Python runtime)
- Restores Claude Desktop config from backup
- Prompts user: "Keep your OMEGA memories?" before touching `%USERPROFILE%\.omega\`

## What the Installer Does NOT Do

- Does not install Claude Desktop (prerequisite)
- Does not require admin privileges
- Does not modify system PATH
- Does not require internet during install (except ONNX model download)

## Distribution

- GitHub Releases on `singularityjason/omega` (private) or `omega-memory/omega-memory` (public)
- Download link on omegamax.co
- Built via GitHub Actions workflow on release tags

## Build Pipeline

GitHub Actions workflow:
1. Check out repo on `windows-latest` runner
2. Download Python 3.12 embeddable package
3. Create venv, install `omega-memory[server]`
4. Run Inno Setup compiler to produce `omega-setup.exe`
5. Upload as release artifact
