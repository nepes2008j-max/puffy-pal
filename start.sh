#!/usr/bin/env bash
# Start Puffy Pal on this laptop: AI server (toy-brain + Whisper + Kokoro) and open the app.
# Usage: ./start.sh            -> opens the live GitHub Pages site (talks to this laptop)
#        ./start.sh local      -> opens http://localhost:5000 instead
#        ./start.sh public     -> also opens a public https link for phones / other networks
set -euo pipefail
cd "$(dirname "$0")"
PY="${PUFFY_PYTHON:-$HOME/Desktop/ai/.venv/bin/python}"

if curl -sf localhost:5000/api/health >/dev/null; then
  echo "Puffy Pal server already running."
else
  echo "Starting Puffy Pal server (first start loads the models, ~20s)..."
  nohup "$PY" server/app.py > server.log 2>&1 &
  for _ in $(seq 1 90); do curl -sf localhost:5000/api/health >/dev/null && break; sleep 1; done
  curl -sf localhost:5000/api/health >/dev/null || { echo "Server didn't start, see server.log"; exit 1; }
fi
curl -s localhost:5000/api/health; echo

URL="https://nepes2008j-max.github.io/puffy-pal/"
[ "${1:-}" = "local" ] && URL="http://localhost:5000/"

if [ "${1:-}" = "public" ]; then
  # Public https link to this laptop (any network, phones too) via a free Cloudflare quick tunnel.
  # The link changes every time the tunnel restarts. Anyone with the link can talk to Puffy Pal.
  CF="${CLOUDFLARED:-$HOME/.local/bin/cloudflared}"
  pkill -f "[c]loudflared tunnel" || true
  nohup "$CF" tunnel --no-autoupdate --url http://localhost:5000 > tunnel.log 2>&1 &
  for _ in $(seq 1 45); do grep -qo 'https://[a-z0-9-]*\.trycloudflare\.com' tunnel.log && break; sleep 1; done
  URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' tunnel.log | head -1)
  [ -n "$URL" ] || { echo "Tunnel didn't start, see tunnel.log"; exit 1; }
  echo "$URL" > public_url.txt
  echo "Public link (works from any network while this laptop is on): $URL"
fi
xdg-open "$URL" >/dev/null 2>&1 || echo "Open $URL"
echo "Stop: pkill -f server/app.py; pkill -f cloudflared"
