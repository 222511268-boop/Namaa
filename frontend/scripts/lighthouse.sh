#!/usr/bin/env bash
# Lighthouse 12 on the five key pages, mobile and desktop, signed in as a manager.
# Same settings as the redesign baseline (docs/redesign/lighthouse/before).
# Optional PAGES="map queue" limits the pages (default: all five; use "sites" for the King Abdullah profile).
# Usage: BASE_URL=http://127.0.0.1:3100 MANAGER_EMAIL=... MANAGER_PASSWORD=... OUT=dir bash scripts/lighthouse.sh
set -euo pipefail
cd "$(dirname "$0")/.."
: "${BASE_URL:?}" "${MANAGER_EMAIL:?}" "${MANAGER_PASSWORD:?}" "${OUT:?}"

TOKEN=$(curl -s -D - -o /dev/null -H "Content-Type: application/json" \
  -d "{\"email\":\"$MANAGER_EMAIL\",\"password\":\"$MANAGER_PASSWORD\"}" "$BASE_URL/api/auth/login" \
  | grep -i "set-cookie" | sed -E 's/.*namaa_session=([^;]+);.*/\1/')
SITE=$(curl -s -b "namaa_session=$TOKEN" "$BASE_URL/api/sites?q=King%20Abdullah" | python -c "import json,sys; print(json.load(sys.stdin)[0]['id'])")
CHROME=$(node -e "console.log(require('@playwright/test').chromium.executablePath())")
HDR="{\"Cookie\":\"namaa_session=$TOKEN\"}"
mkdir -p "$OUT"
if [ -n "${PAGES:-}" ]; then read -r -a LIST <<< "$PAGES"; else LIST=(login "" map queue "sites/$SITE"); fi

for ff in mobile desktop; do
  PRESET=""
  [ "$ff" = desktop ] && PRESET="--preset=desktop"
  for p in "${LIST[@]}"; do
    [ "$p" = sites ] && p="sites/$SITE"
    [ "$p" = overview ] && p=""
    name=$(echo "${p:-overview}" | cut -d/ -f1)
    npx --yes lighthouse@12 "$BASE_URL/$p" --chrome-path="$CHROME" --chrome-flags="--headless=new" \
      --extra-headers="$HDR" $PRESET --only-categories=performance,accessibility,best-practices \
      --output=json --output-path="$OUT/$name-$ff.json" --quiet 2>/dev/null || true
    python - "$OUT/$name-$ff.json" "$ff" "$name" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8")); c = d["categories"]; a = d["audits"]
print(sys.argv[2], sys.argv[3].ljust(8), "perf", round(c["performance"]["score"] * 100),
      "a11y", round(c["accessibility"]["score"] * 100), "bp", round(c["best-practices"]["score"] * 100),
      "LCP", a["largest-contentful-paint"]["displayValue"], "CLS", a["cumulative-layout-shift"]["displayValue"],
      "TBT", a["total-blocking-time"]["displayValue"])
PY
  done
done
