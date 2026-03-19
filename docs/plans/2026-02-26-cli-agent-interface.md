# CLI Agent Interface (OMEGA_JSON + --json expansion) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make OMEGA's CLI a universal agent interface by adding `OMEGA_JSON=1` env var support and `--json` output to 4 key commands (`store`, `remember`, `status`, `doctor`), completing the write→read→verify agent loop.

**Architecture:** Add a single `_use_json(args)` helper that checks both the `--json` flag and `OMEGA_JSON=1` env var. Retrofit existing 5 JSON commands to use it. Add JSON output paths to 4 new commands. All changes in `cli.py` + `test_cli.py`. Core tier (public-safe).

**Tech Stack:** Python 3.11, argparse, json stdlib, pytest

---

### Task 1: Add `_use_json()` helper

**Files:**
- Modify: `src/omega/cli.py:15-16` (after `logger = logging.getLogger(...)`)
- Test: `tests/test_cli.py`

**Step 1: Write the failing tests**

Add to `tests/test_cli.py` — new import and test class:

```python
# Add to imports at top:
from omega.cli import _use_json

# New test class after TestCLITypeMap:

class TestUseJson:
    """Tests for _use_json() helper."""

    def test_false_by_default(self):
        args = argparse.Namespace()
        assert _use_json(args) is False

    def test_true_when_json_flag_set(self):
        args = argparse.Namespace(json=True)
        assert _use_json(args) is True

    def test_false_when_json_flag_false(self):
        args = argparse.Namespace(json=False)
        assert _use_json(args) is False

    def test_true_when_env_var_set(self, monkeypatch):
        monkeypatch.setenv("OMEGA_JSON", "1")
        args = argparse.Namespace()
        assert _use_json(args) is True

    def test_false_when_env_var_not_1(self, monkeypatch):
        monkeypatch.setenv("OMEGA_JSON", "true")
        args = argparse.Namespace()
        assert _use_json(args) is False

    def test_env_var_overrides_missing_flag(self, monkeypatch):
        monkeypatch.setenv("OMEGA_JSON", "1")
        args = argparse.Namespace()  # no json attr
        assert _use_json(args) is True

    def test_flag_works_without_env_var(self, monkeypatch):
        monkeypatch.delenv("OMEGA_JSON", raising=False)
        args = argparse.Namespace(json=True)
        assert _use_json(args) is True
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_cli.py::TestUseJson -v`
Expected: FAIL — `ImportError: cannot import name '_use_json'`

**Step 3: Write the implementation**

In `src/omega/cli.py`, add after line 15 (`logger = logging.getLogger("omega.cli")`):

```python
def _use_json(args) -> bool:
    """Check if JSON output requested via --json flag or OMEGA_JSON=1 env var."""
    return getattr(args, "json", False) or os.environ.get("OMEGA_JSON") == "1"
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_cli.py::TestUseJson -v`
Expected: All 7 PASS

**Step 5: Commit**

```bash
git add src/omega/cli.py tests/test_cli.py
git commit -m "feat(cli): add _use_json() helper with OMEGA_JSON=1 env var support"
```

---

### Task 2: Retrofit existing 5 commands to use `_use_json()`

**Files:**
- Modify: `src/omega/cli.py` (lines 306, 429, 1020, 1051, 1960)
- Test: `tests/test_cli.py`

**Step 1: Write the failing test**

Add a test proving `OMEGA_JSON=1` works with `cmd_query` (the existing commands already have `--json` tests, so this test validates the env var path):

```python
class TestOmegaJsonEnvVar:
    """Tests that OMEGA_JSON=1 env var triggers JSON output on existing commands."""

    def test_query_respects_env_var(self, capsys, monkeypatch):
        monkeypatch.setenv("OMEGA_JSON", "1")
        mock_results = [{"content": "env var test", "relevance": 0.9, "event_type": "memory"}]
        args = argparse.Namespace(query_text=["hello"], limit=10, json=False, exact=False)
        with patch("omega.cli.time") as mock_time:
            mock_time.monotonic.side_effect = [0.0, 0.02]
            with patch("omega.bridge.query_structured", return_value=mock_results):
                cmd_query(args)
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["count"] == 1
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_cli.py::TestOmegaJsonEnvVar -v`
Expected: FAIL — output is Rich text, not JSON (json.loads will raise)

**Step 3: Replace all `getattr(args, "json", False)` with `_use_json(args)`**

In `src/omega/cli.py`, make these 5 replacements:

- Line 306: `use_json = getattr(args, "json", False)` → `use_json = _use_json(args)`
- Line 429: `use_json = getattr(args, "json", False)` → `use_json = _use_json(args)`
- Line 1020: `use_json = getattr(args, "json", False)` → `use_json = _use_json(args)`
- Line 1051: `use_json = getattr(args, "json", False)` → `use_json = _use_json(args)`
- Line 1960: `use_json = getattr(args, "json", False)` → `use_json = _use_json(args)`

**Step 4: Run tests to verify they pass**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_cli.py -v`
Expected: All PASS (existing tests unchanged, new env var test passes)

**Step 5: Commit**

```bash
git add src/omega/cli.py tests/test_cli.py
git commit -m "refactor(cli): use _use_json() across all existing JSON commands"
```

---

### Task 3: Add `--json` to `cmd_store`

**Files:**
- Modify: `src/omega/cli.py` — `cmd_store()` (line 397) and store parser (line 2008)
- Test: `tests/test_cli.py`

**Step 1: Write the failing tests**

Add to `TestCmdStore`:

```python
    def test_json_output_mode(self, capsys):
        """--json flag should output JSON with status and content."""
        args = argparse.Namespace(content=["test", "memory"], type="memory", json=True)
        with patch("omega.bridge.store") as mock_store:
            cmd_store(args)
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["status"] == "ok"
        assert parsed["content"] == "test memory"
        assert parsed["type"] == "memory"

    def test_json_via_env_var(self, capsys, monkeypatch):
        """OMEGA_JSON=1 should trigger JSON output."""
        monkeypatch.setenv("OMEGA_JSON", "1")
        args = argparse.Namespace(content=["env", "test"], type="decision", json=False)
        with patch("omega.bridge.store"):
            cmd_store(args)
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["status"] == "ok"
        assert parsed["type"] == "decision"
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_cli.py::TestCmdStore::test_json_output_mode -v`
Expected: FAIL — `json.loads` fails on `"Stored [memory]: test memory"`

**Step 3: Implement JSON output in `cmd_store`**

Replace `cmd_store` (lines 397-410):

```python
def cmd_store(args):
    """Store a memory with a specified type."""
    content = " ".join(args.content)
    if not content.strip():
        print("Usage: omega store <text> [-t TYPE]", file=sys.stderr)
        sys.exit(1)

    cli_type = getattr(args, "type", "memory")
    event_type = _CLI_TYPE_MAP.get(cli_type, cli_type)

    from omega.bridge import store

    store(content=content, event_type=event_type)

    if _use_json(args):
        print(json.dumps({"status": "ok", "content": content[:200], "type": cli_type}, indent=2))
    else:
        print(f"Stored [{cli_type}]: {content[:80]}")
```

Add `--json` to the store parser (after line 2016, the `help="Memory type"` line):

```python
    store_parser.add_argument("--json", action="store_true", help="Output as JSON (also: OMEGA_JSON=1)")
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_cli.py::TestCmdStore -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/omega/cli.py tests/test_cli.py
git commit -m "feat(cli): add --json output to store command"
```

---

### Task 4: Add `--json` to `cmd_remember`

**Files:**
- Modify: `src/omega/cli.py` — `cmd_remember()` (line 413) and remember parser (line 2018)
- Test: `tests/test_cli.py`

**Step 1: Write the failing tests**

Add to `TestCmdRemember`:

```python
    def test_json_output_mode(self, capsys):
        """--json flag should output JSON with status and content."""
        args = argparse.Namespace(text=["prefer", "dark", "mode"], json=True)
        with patch("omega.bridge.remember", return_value={"status": "ok"}):
            cmd_remember(args)
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["status"] == "ok"
        assert parsed["content"] == "prefer dark mode"

    def test_json_via_env_var(self, capsys, monkeypatch):
        """OMEGA_JSON=1 should trigger JSON output."""
        monkeypatch.setenv("OMEGA_JSON", "1")
        args = argparse.Namespace(text=["use", "vim"], json=False)
        with patch("omega.bridge.remember", return_value={"status": "ok"}):
            cmd_remember(args)
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["status"] == "ok"
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_cli.py::TestCmdRemember::test_json_output_mode -v`
Expected: FAIL

**Step 3: Implement JSON output in `cmd_remember`**

Replace `cmd_remember` (lines 413-423):

```python
def cmd_remember(args):
    """Store a permanent user preference."""
    text = " ".join(args.text)
    if not text.strip():
        print("Usage: omega remember <text>", file=sys.stderr)
        sys.exit(1)

    from omega.bridge import remember

    remember(text=text)

    if _use_json(args):
        print(json.dumps({"status": "ok", "content": text[:200]}, indent=2))
    else:
        print(f"Remembered: {text[:120]}")
```

Add `--json` to the remember parser (after line 2019):

```python
    remember_parser.add_argument("--json", action="store_true", help="Output as JSON (also: OMEGA_JSON=1)")
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_cli.py::TestCmdRemember -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/omega/cli.py tests/test_cli.py
git commit -m "feat(cli): add --json output to remember command"
```

---

### Task 5: Add `--json` to `cmd_status`

**Files:**
- Modify: `src/omega/cli.py` — `cmd_status()` (line 706) and status parser (line 2041)
- Test: `tests/test_cli.py`

**Step 1: Write the failing test**

Add new test class:

```python
class TestCmdStatus:
    """Tests for cmd_status() CLI command."""

    def test_json_output_mode(self, capsys, tmp_path, monkeypatch):
        """--json flag should output structured JSON status."""
        import sqlite3

        # Create a minimal omega.db
        db_path = tmp_path / "omega.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE memories (id TEXT, content TEXT, metadata TEXT)")
        conn.execute("INSERT INTO memories VALUES ('m1', 'test', '{}')")
        conn.commit()
        conn.close()

        monkeypatch.setattr("omega.cli.OMEGA_DIR", tmp_path)
        monkeypatch.setattr("omega.cli.BGE_MODEL_DIR", tmp_path / "no-model")
        monkeypatch.setattr("omega.cli.MINILM_MODEL_DIR", tmp_path / "no-model")

        args = argparse.Namespace(json=True)
        cmd_status(args)
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["backend"] == "sqlite"
        assert parsed["memories"] == 1
        assert "size_mb" in parsed

    def test_json_via_env_var(self, capsys, tmp_path, monkeypatch):
        """OMEGA_JSON=1 should trigger JSON output."""
        import sqlite3

        db_path = tmp_path / "omega.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE memories (id TEXT, content TEXT, metadata TEXT)")
        conn.commit()
        conn.close()

        monkeypatch.setenv("OMEGA_JSON", "1")
        monkeypatch.setattr("omega.cli.OMEGA_DIR", tmp_path)
        monkeypatch.setattr("omega.cli.BGE_MODEL_DIR", tmp_path / "no-model")
        monkeypatch.setattr("omega.cli.MINILM_MODEL_DIR", tmp_path / "no-model")

        args = argparse.Namespace(json=False)
        cmd_status(args)
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert "backend" in parsed
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_cli.py::TestCmdStatus -v`
Expected: FAIL — output is Rich panel, not JSON

**Step 3: Implement JSON output in `cmd_status`**

Replace the entire `cmd_status` function (lines 706-812). The strategy: collect all data into a dict, then either print JSON or Rich output.

```python
def cmd_status(args):
    """Show OMEGA status: memory count, store size, model status."""
    use_json = _use_json(args)
    data = {}

    # SQLite database (primary backend)
    db_path = OMEGA_DIR / "omega.db"
    if db_path.exists():
        import sqlite3

        size_mb = db_path.stat().st_size / (1024 * 1024)
        data["backend"] = "sqlite"
        data["database"] = str(db_path)
        data["size_mb"] = round(size_mb, 2)
        try:
            conn = sqlite3.connect(str(db_path), timeout=30)
            count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            data["memories"] = count
            try:
                import sqlite_vec

                conn.enable_load_extension(True)
                sqlite_vec.load(conn)
                conn.enable_load_extension(False)
                data["vector_search"] = True
            except Exception:
                data["vector_search"] = False
            conn.close()
        except Exception as e:
            data["error"] = str(e)
    else:
        store_path = OMEGA_DIR / "store.jsonl"
        if store_path.exists():
            size_mb = store_path.stat().st_size / (1024 * 1024)
            with open(store_path) as f:
                line_count = sum(1 for _ in f)
            data["backend"] = "jsonl"
            data["store"] = str(store_path)
            data["memories"] = line_count
            data["size_mb"] = round(size_mb, 2)
        else:
            data["backend"] = None
            data["memories"] = 0

    # Model
    bge_path = BGE_MODEL_DIR / "model.onnx"
    minilm_path = MINILM_MODEL_DIR / "model.onnx"
    if bge_path.exists():
        data["model"] = "bge-small-en-v1.5"
        data["model_size_mb"] = round(bge_path.stat().st_size / (1024 * 1024), 0)
    elif minilm_path.exists():
        data["model"] = "all-MiniLM-L6-v2"
        data["model_size_mb"] = round(minilm_path.stat().st_size / (1024 * 1024), 0)
    else:
        data["model"] = None

    # Profile
    profile_path = OMEGA_DIR / "profile.json"
    data["has_profile"] = profile_path.exists()

    # Config version
    config_path = OMEGA_DIR / "config.json"
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
            data["version"] = config.get("version", "unknown")
        except Exception:
            pass

    # Cloud
    secrets_path = OMEGA_DIR / "secrets.json"
    cloud = {"configured": secrets_path.exists()}
    if cloud["configured"]:
        for marker_name, key in [("last-cloud-pull", "last_pull"), ("last-cloud-push", "last_push")]:
            marker = OMEGA_DIR / marker_name
            if marker.exists():
                try:
                    cloud[key] = marker.read_text().strip()
                except Exception:
                    pass
    data["cloud"] = cloud

    if use_json:
        print(json.dumps(data, indent=2, default=str))
        return

    # Rich/plain output (existing behavior preserved)
    from omega.cli_ui import print_header, print_kv

    print_header("OMEGA Status")
    kv: list[tuple[str, str]] = []

    if data.get("backend") == "sqlite":
        kv.append(("Backend", "SQLite"))
        kv.append(("Database", data.get("database", "")))
        kv.append(("Size", f"{data.get('size_mb', 0):.2f} MB"))
        kv.append(("Memories", str(data.get("memories", 0))))
        if data.get("vector_search"):
            kv.append(("Vector search", "enabled (sqlite-vec)"))
        else:
            kv.append(("Vector search", "text-only fallback"))
        if "error" in data:
            kv.append(("Error", data["error"]))
    elif data.get("backend") == "jsonl":
        kv.append(("Backend", "JSONL (legacy)"))
        kv.append(("Store", data.get("store", "")))
        kv.append(("Memories", str(data.get("memories", 0))))
        kv.append(("Size", f"{data.get('size_mb', 0):.2f} MB"))
        kv.append(("Tip", "Run 'omega migrate-db' to upgrade to SQLite"))
    else:
        kv.append(("Store", "not initialized"))
        kv.append(("Memories", "0"))

    if data.get("model"):
        model_label = data["model"]
        if data.get("model_size_mb"):
            model_label += f" ONNX ({data['model_size_mb']:.0f} MB)"
        kv.append(("Model", model_label))
        if data["model"] == "all-MiniLM-L6-v2":
            kv.append(("Tip", "Run 'omega setup --download-model' to upgrade to bge-small-en-v1.5"))
    else:
        kv.append(("Model", "not downloaded"))
        kv.append(("Tip", "Run 'omega setup' to download"))

    # Legacy graphs
    graphs_dir = OMEGA_DIR / "graphs"
    if graphs_dir.exists():
        graph_files = list(graphs_dir.glob("*.json"))
        if graph_files:
            kv.append(("Legacy graphs", f"{len(graph_files)} files (run 'omega migrate-db' to convert)"))

    if data.get("has_profile"):
        kv.append(("Profile", str(OMEGA_DIR / "profile.json")))

    if data.get("version"):
        kv.append(("Version", data["version"]))

    print_kv(kv)

    cloud = data.get("cloud", {})
    if cloud.get("configured"):
        cloud_kv = [("Cloud", "configured")]
        if cloud.get("last_pull"):
            cloud_kv.append(("Last pull", cloud["last_pull"]))
        if cloud.get("last_push"):
            cloud_kv.append(("Last push", cloud["last_push"]))
        print_kv(cloud_kv)
    else:
        print_kv([("Cloud", "not configured")])

    print()
```

Add `--json` to the status parser. Replace line 2041:

```python
    status_parser = subparsers.add_parser("status", help="Show memory count, store size, model status")
    status_parser.add_argument("--json", action="store_true", help="Output as JSON (also: OMEGA_JSON=1)")
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_cli.py::TestCmdStatus -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/omega/cli.py tests/test_cli.py
git commit -m "feat(cli): add --json output to status command"
```

---

### Task 6: Add `--json` to `cmd_doctor`

**Files:**
- Modify: `src/omega/cli.py` — `cmd_doctor()` (line 1389) and doctor parser (line 2043)
- Test: `tests/test_cli.py`

**Step 1: Write the failing test**

```python
class TestCmdDoctor:
    """Tests for cmd_doctor() JSON output."""

    def test_json_output_mode(self, capsys, tmp_path, monkeypatch):
        """--json flag should output structured JSON checks."""
        import sqlite3

        # Create a minimal omega.db with memories + FTS
        db_path = tmp_path / "omega.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE memories (id TEXT, content TEXT, metadata TEXT)")
        conn.execute("CREATE VIRTUAL TABLE memories_fts USING fts5(content)")
        conn.execute("CREATE TABLE memories_vec (rowid INTEGER PRIMARY KEY, embedding BLOB)")
        conn.execute("INSERT INTO memories VALUES ('m1', 'test', '{}')")
        conn.execute("INSERT INTO memories_fts VALUES ('test')")
        conn.commit()
        conn.close()

        monkeypatch.setattr("omega.cli.OMEGA_DIR", tmp_path)
        monkeypatch.setattr("omega.cli.BGE_MODEL_DIR", tmp_path / "no-model")
        monkeypatch.setattr("omega.cli.MINILM_MODEL_DIR", tmp_path / "no-model")
        monkeypatch.setattr("omega.cli.SETTINGS_JSON_PATH", tmp_path / "no-settings")

        args = argparse.Namespace(json=True, client=None)
        with pytest.raises(SystemExit) as exc_info:
            cmd_doctor(args)
        # Will have errors (model not found) but should still output JSON
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert "checks" in parsed
        assert isinstance(parsed["checks"], list)
        assert "errors" in parsed
        assert "warnings" in parsed
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_cli.py::TestCmdDoctor::test_json_output_mode -v`
Expected: FAIL — output is Rich text, not JSON

**Step 3: Implement JSON output in `cmd_doctor`**

The strategy: modify the `ok()`, `fail()`, `warn()` closures to accumulate checks into a list, and suppress Rich output when in JSON mode. At the end, print JSON instead of the Rich summary.

At the top of `cmd_doctor`, add after the imports (line 1391):

```python
    use_json = _use_json(args)
    checks = []
```

Replace the three closures (lines 1396-1407):

```python
    def ok(msg):
        checks.append({"status": "ok", "message": msg})
        if not use_json:
            print_status_line("ok", msg)

    def fail(msg):
        nonlocal errors
        errors += 1
        checks.append({"status": "fail", "message": msg})
        if not use_json:
            print_status_line("fail", msg)

    def warn(msg):
        nonlocal warnings
        warnings += 1
        checks.append({"status": "warn", "message": msg})
        if not use_json:
            print_status_line("warn", msg)
```

Wrap the Rich-only calls with `if not use_json:` guards:

- Line 1409 (`print_header`): `if not use_json: print_header("OMEGA Doctor")`
- All `print_section(...)` calls: wrap each with `if not use_json:`
- Line 1419 (`print(f"\n{errors}...`): `if not use_json: print(...)`
- Lines 1656 (`print(f"    {line[:120]}")`): `if not use_json: print(...)`
- Line 1527 (`print("    Run: claude mcp add...")`): `if not use_json: print(...)`
- Line 1562 (`print("    Fix: INSERT INTO...")`): `if not use_json: print(...)`

Replace the summary block at the end (lines 1708-1710):

```python
    print()
    if use_json:
        print(json.dumps({"checks": checks, "errors": errors, "warnings": warnings}, indent=2))
    else:
        print_summary(errors, warnings)
    sys.exit(1 if errors > 0 else 0)
```

Add `--json` to the doctor parser (after line 2043):

```python
    doctor_parser.add_argument("--json", action="store_true", help="Output as JSON (also: OMEGA_JSON=1)")
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_cli.py::TestCmdDoctor -v`
Expected: All PASS

Also run the full CLI test suite to confirm no regressions:

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_cli.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/omega/cli.py tests/test_cli.py
git commit -m "feat(cli): add --json output to doctor command"
```

---

### Task 7: Update help text for existing `--json` flags

**Files:**
- Modify: `src/omega/cli.py` (parser definitions only)

**Step 1: No test needed (help text only)**

**Step 2: Update the 5 existing `--json` help strings to mention the env var**

Replace in the parser section:

- Line 2006: `help="Output as JSON"` → `help="Output as JSON (also: OMEGA_JSON=1)"`
- Line 2023: `help="Output as JSON"` → `help="Output as JSON (also: OMEGA_JSON=1)"`
- Line 2068: `help="Output as JSON"` → `help="Output as JSON (also: OMEGA_JSON=1)"`
- Line 2071: `help="Output as JSON"` → `help="Output as JSON (also: OMEGA_JSON=1)"`
- Line 2157: `help="Output as JSON to stdout"` → `help="Output as JSON to stdout (also: OMEGA_JSON=1)"`

**Step 3: Run full test suite**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_cli.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add src/omega/cli.py
git commit -m "docs(cli): mention OMEGA_JSON=1 env var in all --json help text"
```

---

### Task 8: Final integration verification

**Step 1: Run the full test suite**

Run: `cd ~/Projects/omega && python3.11 -m pytest tests/test_cli.py -v`
Expected: All PASS

**Step 2: Manual smoke test (if OMEGA is installed)**

```bash
cd ~/Projects/omega
# Human mode (existing behavior)
python3.11 -m omega status
python3.11 -m omega doctor

# Flag mode
python3.11 -m omega status --json
python3.11 -m omega doctor --json

# Env var mode (agent simulation)
OMEGA_JSON=1 python3.11 -m omega status
OMEGA_JSON=1 python3.11 -m omega store "test from CLI" -t decision
OMEGA_JSON=1 python3.11 -m omega query "test from CLI"
```

**Step 3: Verify all JSON output is valid**

```bash
python3.11 -m omega status --json | python3.11 -m json.tool
python3.11 -m omega doctor --json | python3.11 -m json.tool
```

Expected: Valid JSON, pretty-printed by `json.tool`

---

## Summary of Changes

| File | Lines Changed | What |
|------|--------------|------|
| `src/omega/cli.py` | ~80 lines | `_use_json()`, 5 retrofits, 4 new JSON paths, help text |
| `tests/test_cli.py` | ~100 lines | 3 new test classes, 2 expanded test classes |

## JSON Schemas (contract for agents)

```
omega store --json    → {"status": "ok", "content": str, "type": str}
omega remember --json → {"status": "ok", "content": str}
omega status --json   → {"backend": str|null, "memories": int, "size_mb": float, "model": str|null, "vector_search": bool, "cloud": {"configured": bool, ...}, ...}
omega doctor --json   → {"checks": [{"status": "ok|fail|warn", "message": str}], "errors": int, "warnings": int}
```
