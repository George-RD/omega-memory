#!/usr/bin/env bash
# prepare-public-repo.sh — Create a clean copy of OMEGA for the public repo
#
# Usage: ./scripts/prepare-public-repo.sh [output_dir]
# Default output: /tmp/omega-public

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_DIR="${1:-/tmp/omega-public}"

echo "=== OMEGA Public Repo Preparation ==="
echo "Source: $SOURCE_DIR"
echo "Output: $OUTPUT_DIR"
echo ""

# ── Safety check ──────────────────────────────────────────────────────────
if [ -d "$OUTPUT_DIR" ]; then
    echo "Output directory already exists: $OUTPUT_DIR"
    read -p "Remove and recreate? [y/N] " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$OUTPUT_DIR"
    else
        echo "Aborted."
        exit 1
    fi
fi

mkdir -p "$OUTPUT_DIR"

# ── Copy core source files ────────────────────────────────────────────────
echo "Copying core source files..."

# Top-level files
for f in README.md CONTRIBUTING.md SECURITY.md CHANGELOG.md LICENSE NOTICE \
         pyproject.toml mkdocs.yml .gitignore .python-version; do
    [ -f "$SOURCE_DIR/$f" ] && cp "$SOURCE_DIR/$f" "$OUTPUT_DIR/$f"
done

# src/omega/ — core Python files only
mkdir -p "$OUTPUT_DIR/src/omega"
CORE_FILES=(
    __init__.py __main__.py bridge.py cli.py cli_ui.py crypto.py
    graphs.py json_compat.py migrate_to_sqlite.py plugins.py
    preferences.py sqlite_store.py task_utils.py types.py
)
for f in "${CORE_FILES[@]}"; do
    [ -f "$SOURCE_DIR/src/omega/$f" ] && cp "$SOURCE_DIR/src/omega/$f" "$OUTPUT_DIR/src/omega/$f"
done

# src/omega/server/ — core server files only (no coord_schemas/coord_handlers)
mkdir -p "$OUTPUT_DIR/src/omega/server"
SERVER_FILES=(__init__.py mcp_server.py handlers.py tool_schemas.py hook_server.py)
for f in "${SERVER_FILES[@]}"; do
    [ -f "$SOURCE_DIR/src/omega/server/$f" ] && cp "$SOURCE_DIR/src/omega/server/$f" "$OUTPUT_DIR/src/omega/server/$f"
done

# src/omega/data/ — core data files only
mkdir -p "$OUTPUT_DIR/src/omega/data"
DATA_FILES=(hooks-core.json claude-md-fragment.md)
for f in "${DATA_FILES[@]}"; do
    [ -f "$SOURCE_DIR/src/omega/data/$f" ] && cp "$SOURCE_DIR/src/omega/data/$f" "$OUTPUT_DIR/src/omega/data/$f"
done

# ── Hooks ─────────────────────────────────────────────────────────────────
echo "Copying core hooks..."
mkdir -p "$OUTPUT_DIR/hooks"
HOOK_FILES=(
    fast_hook.py session_start.py session_stop.py auto_capture.py
    surface_memories.py
)
for f in "${HOOK_FILES[@]}"; do
    [ -f "$SOURCE_DIR/hooks/$f" ] && cp "$SOURCE_DIR/hooks/$f" "$OUTPUT_DIR/hooks/$f"
done

# ── Tests — core only ────────────────────────────────────────────────────
echo "Copying core tests..."
mkdir -p "$OUTPUT_DIR/tests"

# Copy conftest and core test files (exclude commercial module tests)
EXCLUDE_TESTS=(
    test_coordination.py test_coordination_loop.py test_edge_and_coord.py
    test_uat_coordination.py test_uat_multi_agent_collab.py
    test_router.py test_uat_router.py
    test_entity.py test_entity_integration.py
    test_knowledge.py
    test_cloud_sync.py
    test_secure_profile.py
    test_pre_file_guard.py test_pre_task_guard.py
    test_uat_cross_module.py
)

# Build exclude pattern for find
EXCLUDE_ARGS=()
for f in "${EXCLUDE_TESTS[@]}"; do
    EXCLUDE_ARGS+=(! -name "$f")
done

# Copy conftest.py
[ -f "$SOURCE_DIR/tests/conftest.py" ] && cp "$SOURCE_DIR/tests/conftest.py" "$OUTPUT_DIR/tests/"

# Copy all test files except excluded ones
for f in "$SOURCE_DIR"/tests/test_*.py; do
    basename_f="$(basename "$f")"
    skip=false
    for excl in "${EXCLUDE_TESTS[@]}"; do
        if [ "$basename_f" = "$excl" ]; then
            skip=true
            break
        fi
    done
    if [ "$skip" = false ]; then
        cp "$f" "$OUTPUT_DIR/tests/"
    fi
done

# ── GitHub config ─────────────────────────────────────────────────────────
echo "Copying GitHub config..."
if [ -d "$SOURCE_DIR/.github" ]; then
    cp -r "$SOURCE_DIR/.github" "$OUTPUT_DIR/.github"
fi

# ── Docs — public only ───────────────────────────────────────────────────
echo "Copying public docs..."
if [ -d "$SOURCE_DIR/docs" ]; then
    cp -r "$SOURCE_DIR/docs" "$OUTPUT_DIR/docs"
    # Remove internal/commercial docs
    rm -rf "$OUTPUT_DIR/docs/internal" "$OUTPUT_DIR/docs/gtm" "$OUTPUT_DIR/docs/legal" "$OUTPUT_DIR/docs/plans"
fi

# ── Verification ──────────────────────────────────────────────────────────
echo ""
echo "=== Verification ==="

# Check no commercial modules leaked
COMMERCIAL_DIRS=(router entity knowledge cloud profile)
LEAKED=false
for d in "${COMMERCIAL_DIRS[@]}"; do
    if [ -d "$OUTPUT_DIR/src/omega/$d" ]; then
        echo "FAIL: Commercial directory leaked: src/omega/$d"
        LEAKED=true
    fi
done

COMMERCIAL_FILES=(coordination.py server/coord_schemas.py server/coord_handlers.py)
for f in "${COMMERCIAL_FILES[@]}"; do
    if [ -f "$OUTPUT_DIR/src/omega/$f" ]; then
        echo "FAIL: Commercial file leaked: src/omega/$f"
        LEAKED=true
    fi
done

# Check no personal identifiers (patterns loaded from external file)
PII_PATTERNS_FILE="$SOURCE_DIR/.pii-patterns"
if [ -f "$PII_PATTERNS_FILE" ]; then
    PII_PATTERN=$(paste -sd '|' "$PII_PATTERNS_FILE")
    PII_COUNT=$(grep -rE "$PII_PATTERN" "$OUTPUT_DIR" 2>/dev/null | grep -v ".git/" | wc -l | tr -d ' ')
    if [ "$PII_COUNT" -gt 0 ]; then
        echo "FAIL: Personal identifiers found ($PII_COUNT matches):"
        grep -rE "$PII_PATTERN" "$OUTPUT_DIR" 2>/dev/null | grep -v ".git/"
        LEAKED=true
    fi
else
    echo "WARN: No .pii-patterns file found at $PII_PATTERNS_FILE — skipping PII check"
fi

# Check no internal docs
for d in internal gtm legal; do
    if [ -d "$OUTPUT_DIR/docs/$d" ]; then
        echo "FAIL: Internal docs leaked: docs/$d"
        LEAKED=true
    fi
done

if [ "$LEAKED" = true ]; then
    echo ""
    echo "FAILED: Leaked files detected. Fix the script before proceeding."
    exit 1
fi

echo "OK: No commercial modules in output"
echo "OK: No personal identifiers found"
echo "OK: No internal docs leaked"

# ── Count files ───────────────────────────────────────────────────────────
SRC_COUNT=$(find "$OUTPUT_DIR/src" -name "*.py" | wc -l | tr -d ' ')
TEST_COUNT=$(find "$OUTPUT_DIR/tests" -name "*.py" | wc -l | tr -d ' ')
echo ""
echo "Source files: $SRC_COUNT"
echo "Test files:   $TEST_COUNT"

# ── Initialize fresh git repo ─────────────────────────────────────────────
echo ""
echo "Initializing fresh git repository..."
cd "$OUTPUT_DIR"
git init -b main
git add -A
git commit -m "Initial release — OMEGA v1.0.0"

# Set remote (don't push automatically)
git remote add origin git@github.com:omega-memory/omega.git

echo ""
echo "=== Done ==="
echo ""
echo "Public repo prepared at: $OUTPUT_DIR"
echo ""
echo "Next steps:"
echo "  cd $OUTPUT_DIR"
echo "  python -m build                    # Build wheel"
echo "  pip install dist/*.whl             # Test install"
echo "  omega --help                       # Verify CLI"
echo "  omega doctor                       # Health check"
echo "  pytest tests/ -x                   # Run core tests"
echo ""
echo "When ready to push:"
echo "  cd $OUTPUT_DIR"
echo "  git push -u origin main"
echo ""
