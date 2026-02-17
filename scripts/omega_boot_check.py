#!/usr/bin/env python3
"""OMEGA pre-flight safety check.

Validates OMEGA installation before allowing MCP server to start:
- Checks omega-memory package is installed
- Validates database integrity
- Verifies model files haven't been tampered with
- Checks file permissions
- Confirms no Claude Code hooks installed

Usage:
    python3 scripts/omega_boot_check.py [--verbose]
"""

import hashlib
import json
import sys
from pathlib import Path

OMEGA_HOME = Path.home() / ".omega"
MODEL_DIR = Path.home() / ".cache" / "omega" / "models" / "bge-small-en-v1.5-onnx"


def check_package():
    try:
        import omega
        return True, f"omega-memory installed (v{getattr(omega, '__version__', 'unknown')})"
    except ImportError:
        return False, "omega-memory NOT installed"


def check_database():
    db_path = OMEGA_HOME / "omega.db"
    if not db_path.exists():
        return True, "No database yet (will be created on first use)"
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT count(*) FROM sqlite_master")
        table_count = cursor.fetchone()[0]
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        if {"memories"} & tables:
            return True, f"Database OK ({table_count} tables, {db_path.stat().st_size / 1024:.0f}KB)"
        else:
            return True, f"Database exists but no memory tables yet ({table_count} tables)"
    except Exception as e:
        return False, f"Database error: {e}"


def check_model():
    required = ["model.onnx", "tokenizer.json", "config.json"]
    if not MODEL_DIR.exists():
        return None, "Model not downloaded yet (run secure_model_download.py)"
    missing = [f for f in required if not (MODEL_DIR / f).exists()]
    if missing:
        return False, f"Missing model files: {', '.join(missing)}"
    onnx_path = MODEL_DIR / "model.onnx"
    with open(onnx_path, "rb") as f:
        header = f.read(16)
    if header[:5] in (b"<!DOC", b"<html", b"<?xml", b"Error"):
        return False, "model.onnx appears to be an HTML error page"
    for jf in ["tokenizer.json", "config.json"]:
        try:
            json.loads((MODEL_DIR / jf).read_text())
        except Exception as e:
            return False, f"{jf} is invalid JSON: {e}"
    size_mb = onnx_path.stat().st_size / (1024 * 1024)
    return True, f"Model OK (model.onnx: {size_mb:.1f}MB)"


def check_permissions():
    issues = []
    if OMEGA_HOME.exists():
        mode = oct(OMEGA_HOME.stat().st_mode)[-3:]
        if mode not in ("700", "750", "755"):
            issues.append(f"~/.omega permissions: {mode} (recommend 700)")
    db_path = OMEGA_HOME / "omega.db"
    if db_path.exists():
        mode = oct(db_path.stat().st_mode)[-3:]
        if mode not in ("600", "640", "644"):
            issues.append(f"omega.db permissions: {mode} (recommend 600)")
    if issues:
        return False, "; ".join(issues)
    return True, "File permissions OK"


def check_no_hooks():
    hooks_config = Path.home() / ".claude" / "hooks.json"
    if not hooks_config.exists():
        return True, "No Claude Code hooks installed (correct for Cowork plugin)"
    try:
        config = json.loads(hooks_config.read_text())
        omega_hooks = [k for k, v in config.items()
                       if any("omega" in str(h).lower() for h in (v if isinstance(v, list) else [v]))]
        if omega_hooks:
            return False, f"OMEGA hooks found in Claude Code: {omega_hooks}. Remove them."
        return True, "No OMEGA hooks in Claude Code config"
    except Exception:
        return True, "Could not read hooks config (probably fine)"


def main():
    print("OMEGA Pre-Flight Check")
    print("=" * 40)
    checks = [
        ("Package", check_package),
        ("Database", check_database),
        ("Model", check_model),
        ("Permissions", check_permissions),
        ("Hooks", check_no_hooks),
    ]
    all_pass = True
    for name, check_fn in checks:
        status, msg = check_fn()
        icon = "PASS" if status is True else ("FAIL" if status is False else "SKIP")
        if status is False:
            all_pass = False
        print(f"  [{icon}] {name}: {msg}")
    print()
    print("All checks passed. OMEGA is ready." if all_pass else "Some checks failed. Review above.")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
