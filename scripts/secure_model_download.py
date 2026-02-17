#!/usr/bin/env python3
"""Secure model download for OMEGA memory system.

Downloads bge-small-en-v1.5 ONNX model from HuggingFace with:
- SHA256 hash verification against pinned values
- File size bounds checking (reject >20% deviation from expected)
- ONNX file header validation
- Atomic download (temp file -> rename on success)

Usage:
    python3 scripts/secure_model_download.py [--target-dir DIR] [--force]
"""

import hashlib
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

HF_REPO = "https://huggingface.co/BAAI/bge-small-en-v1.5/resolve/main"

MODEL_FILES = {
    "model.onnx": {
        "url": f"{HF_REPO}/onnx/model.onnx",
        "expected_size_bytes": 133_000_000,
        "size_tolerance": 0.20,
        "sha256": "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66",  # Pin after first verified download
    },
    "tokenizer.json": {
        "url": f"{HF_REPO}/tokenizer.json",
        "expected_size_bytes": 711_000,
        "size_tolerance": 0.20,
        "sha256": "094f8e891b932f2000c92cfc663bac4c62069f5d8af5b5278c4306aef3084750",
    },
    "config.json": {
        "url": f"{HF_REPO}/config.json",
        "expected_size_bytes": 800,
        "size_tolerance": 0.50,
        "sha256": "9261e7d79b44c8195c1cada2b453e55b00aeb81e907a6664974b4d7776172ab3",
    },
    "tokenizer_config.json": {
        "url": f"{HF_REPO}/tokenizer_config.json",
        "expected_size_bytes": 366,
        "size_tolerance": 0.50,
        "sha256": None,
    },
}

DEFAULT_TARGET = Path.home() / ".cache" / "omega" / "models" / "bge-small-en-v1.5-onnx"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_onnx_header(path: Path) -> bool:
    with open(path, "rb") as f:
        header = f.read(32)
    if len(header) < 8:
        return False
    if header[:5] in (b"<!DOC", b"<html", b"<?xml", b"Error"):
        return False
    if header[0] not in (0x08, 0x0A, 0x10, 0x12, 0x18, 0x1A, 0x20, 0x22):
        return False
    return True


def download_file(url: str, target: Path, retries: int = 3) -> None:
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "omega-memory-secure/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                tmp = target.with_suffix(target.suffix + ".tmp")
                try:
                    with open(tmp, "wb") as f:
                        while True:
                            chunk = resp.read(64 * 1024)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total > 0:
                                pct = downloaded * 100 // total
                                mb = downloaded / (1024 * 1024)
                                print(f"\r    {target.name}: {mb:.1f}MB ({pct}%)", end="", flush=True)
                    print()
                    tmp.rename(target)
                    return
                except Exception:
                    tmp.unlink(missing_ok=True)
                    raise
        except Exception as e:
            if attempt < retries:
                import time
                wait = 2 ** attempt
                print(f"\n    Retry {attempt}/{retries} after {wait}s: {e}")
                time.sleep(wait)
            else:
                raise


def scan_file(fname: str, spec: dict, path: Path) -> list[str]:
    issues = []
    actual_size = path.stat().st_size
    expected = spec["expected_size_bytes"]
    tolerance = spec["size_tolerance"]
    lower = int(expected * (1 - tolerance))
    upper = int(expected * (1 + tolerance))
    if actual_size < lower or actual_size > upper:
        issues.append(f"SIZE MISMATCH: {fname} is {actual_size:,} bytes (expected {expected:,} +/- {tolerance*100:.0f}%)")
    actual_hash = sha256_file(path)
    if spec["sha256"] is not None:
        if actual_hash != spec["sha256"]:
            issues.append(f"HASH MISMATCH: {fname}\n    Expected: {spec['sha256']}\n    Got:      {actual_hash}")
    else:
        print(f"    [INFO] {fname} SHA256: {actual_hash}")
        print(f"           Pin this hash in MODEL_FILES for future verification.")
    if fname.endswith(".onnx"):
        if not validate_onnx_header(path):
            issues.append(f"ONNX VALIDATION FAILED: {fname}")
    if fname.endswith(".json"):
        import json
        try:
            with open(path) as f:
                json.load(f)
        except json.JSONDecodeError as e:
            issues.append(f"INVALID JSON: {fname}: {e}")
    return issues


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Securely download OMEGA embedding model")
    parser.add_argument("--target-dir", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--force", action="store_true", help="Re-download even if files exist")
    parser.add_argument("--check-only", action="store_true", help="Only verify existing files")
    args = parser.parse_args()
    target_dir = args.target_dir
    print(f"OMEGA Secure Model Download\n  Target: {target_dir}\n")
    if args.check_only:
        print("  Mode: CHECK ONLY")
        all_ok = True
        for fname, spec in MODEL_FILES.items():
            fpath = target_dir / fname
            if not fpath.exists():
                print(f"  MISSING: {fname}"); all_ok = False; continue
            issues = scan_file(fname, spec, fpath)
            if issues:
                for i in issues: print(f"  FAIL: {i}")
                all_ok = False
            else:
                print(f"  OK: {fname}")
        sys.exit(0 if all_ok else 1)
    required = ["model.onnx", "tokenizer.json", "config.json"]
    if not args.force and all((target_dir / f).exists() for f in required):
        print("  Model files already present. Running verification...")
        all_ok = True
        for fname, spec in MODEL_FILES.items():
            fpath = target_dir / fname
            if fpath.exists():
                issues = scan_file(fname, spec, fpath)
                if issues:
                    for i in issues: print(f"  FAIL: {i}")
                    all_ok = False
                else:
                    print(f"  OK: {fname}")
        sys.exit(0 if all_ok else 1)
    print("  Step 1: Downloading to staging area...")
    with tempfile.TemporaryDirectory(prefix="omega-model-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        all_issues = []
        for fname, spec in MODEL_FILES.items():
            print(f"  Downloading {fname}...")
            try:
                download_file(spec["url"], tmp_path / fname)
            except Exception as e:
                all_issues.append(f"DOWNLOAD FAILED: {fname}: {e}"); continue
        if all_issues:
            for i in all_issues: print(f"    {i}")
            sys.exit(1)
        print("\n  Step 2: Security scanning...")
        for fname, spec in MODEL_FILES.items():
            fpath = tmp_path / fname
            if not fpath.exists():
                all_issues.append(f"MISSING: {fname}"); continue
            all_issues.extend(scan_file(fname, spec, fpath))
        if all_issues:
            print("\n  SECURITY SCAN FAILED:")
            for i in all_issues: print(f"    {i}")
            sys.exit(1)
        print("\n  Step 3: Installing verified model files...")
        target_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        import shutil
        for fname in MODEL_FILES:
            src = tmp_path / fname
            dst = target_dir / fname
            if src.exists():
                shutil.copy2(src, dst); dst.chmod(0o600)
                print(f"    Installed: {fname}")
    print(f"\n  Model installed to {target_dir}\n  All security checks passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
