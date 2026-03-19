#!/usr/bin/env bash
# Build the OMEGA Pro wheel with correct package metadata.
#
# Usage: ./scripts/build-pro-wheel.sh
#
# Temporarily swaps pyproject.toml to use the Pro name/version,
# builds the wheel, then restores the original. Output: dist/

set -euo pipefail
cd "$(dirname "$0")/.."

PRO_VERSION="${1:-1.2.0}"
DIST_DIR="dist"

echo "Building omega-memory-pro ${PRO_VERSION}..."

# Backup original pyproject.toml
cp pyproject.toml pyproject.toml.bak

# Patch name and version for Pro build
python3.11 -c "
import re, pathlib
p = pathlib.Path('pyproject.toml')
text = p.read_text()
text = re.sub(r'^name = \"omega-memory\"', 'name = \"omega-memory-pro\"', text, count=1, flags=re.MULTILINE)
text = re.sub(r'^version = \"[^\"]+\"', 'version = \"${PRO_VERSION}\"', text, count=1, flags=re.MULTILINE)
text = re.sub(r'^license = \"Apache-2.0\"', 'license = \"LicenseRef-Proprietary\"', text, count=1, flags=re.MULTILINE)
text = re.sub(r'^description = \"[^\"]+\"', 'description = \"OMEGA Pro: coordination, cloud sync, knowledge, and advanced features\"', text, count=1, flags=re.MULTILINE)
# Add omega-memory as dependency
text = text.replace(
    'dependencies = [',
    'dependencies = [\n    \"omega-memory[server]>=${PRO_VERSION}\",',
)
p.write_text(text)
"

# Build
python3.11 -m build --wheel --outdir "$DIST_DIR" 2>&1

# Restore original
mv pyproject.toml.bak pyproject.toml

WHEEL=$(ls -1 "$DIST_DIR"/omega_memory_pro-*.whl 2>/dev/null | tail -1)
if [[ -n "$WHEEL" ]]; then
    echo ""
    echo "Built: $WHEEL"
    echo "Size:  $(du -h "$WHEEL" | cut -f1)"
    echo ""
    echo "Install: pip install $WHEEL"
else
    echo "ERROR: No wheel produced" >&2
    exit 1
fi
