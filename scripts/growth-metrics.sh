#!/bin/bash
# OMEGA Growth Metrics Tracker
# Run weekly: ./scripts/growth-metrics.sh
# Appends to docs/growth-metrics-log.csv

set -euo pipefail

METRICS_FILE="$(dirname "$0")/../docs/growth-metrics-log.csv"
DATE=$(date +%Y-%m-%d)

# Create header if file doesn't exist
if [ ! -f "$METRICS_FILE" ]; then
    echo "date,stars,forks,watchers,open_issues,contributors,pypi_day,pypi_week,pypi_month,x_followers,awesome_merged,awesome_open" > "$METRICS_FILE"
fi

# GitHub metrics
GITHUB=$(gh api repos/omega-memory/omega-memory --jq '{s:.stargazers_count,f:.forks_count,w:.subscribers_count,i:.open_issues_count}' 2>/dev/null || echo '{"s":0,"f":0,"w":0,"i":0}')
STARS=$(echo "$GITHUB" | python3 -c "import json,sys; print(json.load(sys.stdin)['s'])")
FORKS=$(echo "$GITHUB" | python3 -c "import json,sys; print(json.load(sys.stdin)['f'])")
WATCHERS=$(echo "$GITHUB" | python3 -c "import json,sys; print(json.load(sys.stdin)['w'])")
ISSUES=$(echo "$GITHUB" | python3 -c "import json,sys; print(json.load(sys.stdin)['i'])")

# Contributors
CONTRIBUTORS=$(gh api repos/omega-memory/omega-memory/contributors --jq 'length' 2>/dev/null || echo "0")

# PyPI downloads
PYPI=$(python3 -c "
import urllib.request, json
try:
    data = json.loads(urllib.request.urlopen('https://pypistats.org/api/packages/omega-memory/recent').read())['data']
    print(f\"{data.get('last_day',0)},{data.get('last_week',0)},{data.get('last_month',0)}\")
except:
    print('0,0,0')
" 2>/dev/null || echo "0,0,0")

# X followers (from admin API if available, otherwise manual)
X_FOLLOWERS=$(python3 -c "
try:
    import urllib.request, json
    # Try the admin dashboard API
    data = json.loads(urllib.request.urlopen('https://omegamax.co/api/admin/diagnostic').read())
    print(data.get('social', {}).get('followers', 0))
except:
    print('0')
" 2>/dev/null || echo "0")

# Awesome-list PR counts
AWESOME_MERGED=$(gh search prs --author singularityjason --state closed --limit 100 --json title 2>/dev/null | python3 -c "
import json,sys
data=json.load(sys.stdin)
merged=[p for p in data if 'omega' in p.get('title','').lower() or 'OMEGA' in p.get('title','')]
print(len(merged))
" 2>/dev/null || echo "0")

AWESOME_OPEN=$(gh search prs --author singularityjason --state open --limit 100 --json title 2>/dev/null | python3 -c "
import json,sys
data=json.load(sys.stdin)
omega=[p for p in data if 'omega' in p.get('title','').lower() or 'OMEGA' in p.get('title','')]
print(len(omega))
" 2>/dev/null || echo "0")

# Append row
echo "$DATE,$STARS,$FORKS,$WATCHERS,$ISSUES,$CONTRIBUTORS,$PYPI,$X_FOLLOWERS,$AWESOME_MERGED,$AWESOME_OPEN" >> "$METRICS_FILE"

# Print summary
echo "=== OMEGA Growth Metrics ($DATE) ==="
echo "Stars:          $STARS"
echo "Forks:          $FORKS"
echo "Watchers:       $WATCHERS"
echo "Open Issues:    $ISSUES"
echo "Contributors:   $CONTRIBUTORS"
echo "PyPI (d/w/m):   $PYPI"
echo "X Followers:    $X_FOLLOWERS"
echo "PRs merged:     $AWESOME_MERGED"
echo "PRs open:       $AWESOME_OPEN"
echo ""
echo "Logged to: $METRICS_FILE"
