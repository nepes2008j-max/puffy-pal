#!/usr/bin/env bash
# Start Puffy Pal on this laptop: AI server (toy-brain + Whisper + Kokoro) and open the app.
# Usage: ./start.sh            -> opens the live GitHub Pages site (talks to this laptop)
#        ./start.sh local      -> opens http://localhost:5000 instead
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
xdg-open "$URL" >/dev/null 2>&1 || echo "Open $URL"
echo "Stop the server with: pkill -f server/app.py"
