#!/usr/bin/env bash
set -euo pipefail
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'

echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
echo -e "${CYAN}  OMEGA Fork Security Check — Pre-Sync Audit  ${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
echo ""

if [ ! -f "pyproject.toml" ] || ! grep -q "omega-memory" pyproject.toml 2>/dev/null; then
    echo -e "${RED}ERROR: Run this from the omega-memory repo root.${NC}"; exit 1
fi

if ! git remote get-url upstream &>/dev/null; then
    echo -e "${YELLOW}Adding upstream remote...${NC}"
    git remote add upstream https://github.com/omega-memory/omega-memory.git
fi

echo -e "${CYAN}Fetching upstream...${NC}"
git fetch upstream --quiet
DIFF_BASE="upstream/main"
echo -e "${CYAN}Comparing HEAD against ${DIFF_BASE}...${NC}"
echo ""

UPSTREAM_NEW=$(git diff --name-only HEAD..."${DIFF_BASE}" 2>/dev/null || git diff --name-only HEAD "${DIFF_BASE}")
if [ -z "$UPSTREAM_NEW" ]; then
    echo -e "${GREEN}No new upstream changes to review.${NC}"; exit 0
fi
echo -e "${CYAN}Files changed upstream:${NC}"
echo "$UPSTREAM_NEW" | head -50
echo ""

ISSUES=0

echo -e "${CYAN}[1/7] Checking for new network calls...${NC}"
NETWORK_PATTERNS="requests\.(get|post|put|delete|patch)|urllib\.request|httpx\.|aiohttp\.|socket\.connect|urlopen|http\.client"
NETWORK_HITS=$(git diff "${DIFF_BASE}" -- 'src/' 'hooks/' | grep -E "^\+" | grep -vE "^\+\+\+" | grep -cE "$NETWORK_PATTERNS" || true)
if [ "$NETWORK_HITS" -gt 0 ]; then
    echo -e "${RED}  FOUND: $NETWORK_HITS new lines with network calls${NC}"
    git diff "${DIFF_BASE}" -- 'src/' 'hooks/' | grep -E "^\+" | grep -vE "^\+\+\+" | grep -E "$NETWORK_PATTERNS" | head -20
    ISSUES=$((ISSUES + 1))
else echo -e "${GREEN}  OK: No new network calls${NC}"; fi
echo ""

echo -e "${CYAN}[2/7] Checking for new subprocess/exec usage...${NC}"
EXEC_PATTERNS="subprocess\.(run|call|Popen|check_output)|os\.system|eval\(|exec\(|__import__"
EXEC_HITS=$(git diff "${DIFF_BASE}" -- 'src/' 'hooks/' | grep -E "^\+" | grep -vE "^\+\+\+" | grep -cE "$EXEC_PATTERNS" || true)
if [ "$EXEC_HITS" -gt 0 ]; then
    echo -e "${YELLOW}  REVIEW: $EXEC_HITS new lines with subprocess/exec${NC}"
    ISSUES=$((ISSUES + 1))
else echo -e "${GREEN}  OK: No new subprocess/exec usage${NC}"; fi
echo ""

echo -e "${CYAN}[3/7] Checking for telemetry/analytics...${NC}"
TELEMETRY_PATTERNS="telemetry|analytics|tracking|phone.?home|sentry|mixpanel|amplitude|posthog|segment|bugsnag|datadog|newrelic"
TELEMETRY_HITS=$(git diff "${DIFF_BASE}" -- 'src/' 'hooks/' | grep -iE "^\+" | grep -vE "^\+\+\+" | grep -ciE "$TELEMETRY_PATTERNS" || true)
if [ "$TELEMETRY_HITS" -gt 0 ]; then
    echo -e "${RED}  FOUND: $TELEMETRY_HITS new lines with telemetry keywords${NC}"
    ISSUES=$((ISSUES + 1))
else echo -e "${GREEN}  OK: No telemetry/analytics${NC}"; fi
echo ""

echo -e "${CYAN}[4/7] Checking for hook data scope changes...${NC}"
HOOK_CHANGES=$(echo "$UPSTREAM_NEW" | grep -cE "hooks/|hook_server\.py|fast_hook\.py" || true)
if [ "$HOOK_CHANGES" -gt 0 ]; then
    echo -e "${YELLOW}  REVIEW: $HOOK_CHANGES hook-related files changed upstream${NC}"
    ISSUES=$((ISSUES + 1))
else echo -e "${GREEN}  OK: No hook changes${NC}"; fi
echo ""

echo -e "${CYAN}[5/7] Checking for dependency changes...${NC}"
DEP_CHANGES=$(git diff "${DIFF_BASE}" -- pyproject.toml | grep -cE "^\+" || true)
if [ "$DEP_CHANGES" -gt 0 ]; then
    echo -e "${YELLOW}  REVIEW: pyproject.toml has upstream changes${NC}"
    git diff "${DIFF_BASE}" -- pyproject.toml | grep -E "^\+.*=" | grep -vE "^\+\+\+" | head -20
    ISSUES=$((ISSUES + 1))
else echo -e "${GREEN}  OK: No dependency changes${NC}"; fi
echo ""

echo -e "${CYAN}[6/7] Checking for model download URL changes...${NC}"
URL_PATTERNS="huggingface\.co|download.*model|model.*download|\.onnx"
URL_HITS=$(git diff "${DIFF_BASE}" -- 'src/' | grep -E "^\+" | grep -vE "^\+\+\+" | grep -cE "$URL_PATTERNS" || true)
if [ "$URL_HITS" -gt 0 ]; then
    echo -e "${YELLOW}  REVIEW: $URL_HITS lines with model download changes${NC}"
    ISSUES=$((ISSUES + 1))
else echo -e "${GREEN}  OK: No model download changes${NC}"; fi
echo ""

echo -e "${CYAN}[7/7] Running bandit on changed Python files...${NC}"
CHANGED_PY=$(echo "$UPSTREAM_NEW" | grep "\.py$" || true)
if [ -n "$CHANGED_PY" ] && command -v bandit &>/dev/null; then
    BANDIT_OUTPUT=$(echo "$CHANGED_PY" | xargs bandit -ll --quiet 2>/dev/null || true)
    if [ -n "$BANDIT_OUTPUT" ]; then
        echo -e "${YELLOW}  REVIEW: Bandit found issues${NC}"
        echo "$BANDIT_OUTPUT" | head -30
        ISSUES=$((ISSUES + 1))
    else echo -e "${GREEN}  OK: Bandit found no medium+ issues${NC}"; fi
elif ! command -v bandit &>/dev/null; then
    echo -e "${YELLOW}  SKIP: bandit not installed (pip install bandit)${NC}"
else echo -e "${GREEN}  OK: No Python files changed${NC}"; fi
echo ""

echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
if [ "$ISSUES" -eq 0 ]; then
    echo -e "${GREEN}  ALL CLEAR — Safe to merge upstream.${NC}"
    echo -e "${GREEN}  Run: git merge upstream/main${NC}"
else
    echo -e "${YELLOW}  $ISSUES area(s) flagged for review.${NC}"
    echo -e "${YELLOW}  Review the items above before merging.${NC}"
fi
echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
