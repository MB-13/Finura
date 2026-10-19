#!/usr/bin/env bash
# Screenshot a preview page with headless Chrome.
#   preview/shot.sh <scenario|gallery> <out.png> [width=1440] [height=900] [theme=light]
# Requires `pnpm preview:ui` running. CHROME=/path/to/chrome overrides the binary.
set -euo pipefail
target="${1:?scenario name or 'gallery'}"; out="${2:?output png}"
w="${3:-1440}"; h="${4:-900}"; theme="${5:-light}"
chrome="${CHROME:-$(command -v google-chrome || command -v chromium || echo /usr/bin/google-chrome)}"
base="${PREVIEW_URL:-http://localhost:5174}"
if [ "$target" = gallery ]; then q="view=gallery"; else q="scenario=$target"; fi
mkdir -p "$(dirname "$out")"
"$chrome" --headless=new --no-sandbox --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
  --virtual-time-budget=8000 --window-size="$w,$h" --screenshot="$out" "$base/?$q&theme=$theme" >/dev/null 2>&1
echo "$out"
