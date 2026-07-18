#!/usr/bin/env bash
# =============================================================================
# EdgeCDSS Jetson setup v2 — fresh rebuild for Jetson Orin Nano (JetPack/Ubuntu)
# Rebuilt 2026-07-18 to replace the lost jetson_cdss_setup.sh.
#
# Run as the normal user (andrew), NOT root:   bash jetson_cdss_setup_v2.sh
# Safe to re-run; each phase is idempotent.
#
# Phases:
#   1. System packages (python3-venv, git)
#   2. Clone/update repo -> ~/pi-cloud-cdss
#   3. Drop in embeddings.py + requirements-server.txt (expected alongside this script)
#   4. Python venv + server dependencies
#   5. .env template (edit before starting!)
#   6. systemd service (edgecdss.service) — starts on boot
#
# NOT done here (separate steps, on purpose):
#   - ChromaDB data (rescue from arcaneone or re-ingest) — server starts with 0 chunks
#   - cloudflared tunnel — after the server answers locally
# =============================================================================
set -euo pipefail

REPO_URL="https://github.com/AI-in-Austere-Medicine-Project/pi-cloud-cdss"
APP_DIR="$HOME/pi-cloud-cdss"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT=8000

echo "=== Phase 1: system packages ==="
sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv python3-dev git curl

echo "=== Phase 2: repo ==="
if [ -d "$APP_DIR/.git" ]; then
    git -C "$APP_DIR" pull --ff-only
else
    git clone "$REPO_URL" "$APP_DIR"
fi

echo "=== Phase 3: missing server files ==="
for f in embeddings.py; do
    if [ -f "$SCRIPT_DIR/$f" ]; then
        cp "$SCRIPT_DIR/$f" "$APP_DIR/server/$f"
        echo "  installed server/$f"
    elif [ ! -f "$APP_DIR/server/$f" ]; then
        echo "  ERROR: $f not found next to this script and not in repo. Aborting."
        exit 1
    fi
done
[ -f "$SCRIPT_DIR/requirements-server.txt" ] && cp "$SCRIPT_DIR/requirements-server.txt" "$APP_DIR/requirements-server.txt"

echo "=== Phase 4: python venv + deps (this is the slow one on ARM) ==="
cd "$APP_DIR"
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/pip install --upgrade pip -q
./.venv/bin/pip install -r requirements-server.txt

echo "=== Phase 5: .env ==="
if [ ! -f "$APP_DIR/server/.env" ]; then
    cat > "$APP_DIR/server/.env" <<'ENV'
# ---- EdgeCDSS server config — FILL THESE IN ----
OPENAI_API_KEY=sk-REPLACE_ME
CDSS_ACCESS_TOKEN=edgecdss-demo-2026

# ChromaDB storage path (embeddings are local/on-device — no API needed for retrieval)
CHROMADB_PATH=/home/andrew/pi-cloud-cdss/server/cache/chromadb

# Debug flag — NEVER 1 in production
EDGECDSS_DEBUG_WARN_ONLY=0
ENV
    chmod 600 "$APP_DIR/server/.env"
    echo "  created server/.env — EDIT IT: nano $APP_DIR/server/.env"
else
    echo "  server/.env already exists — left untouched"
fi

echo "=== Phase 6: systemd service ==="
sudo tee /etc/systemd/system/edgecdss.service > /dev/null <<UNIT
[Unit]
Description=EdgeCDSS FastAPI server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR/server
ExecStart=$APP_DIR/.venv/bin/uvicorn main:app --host 0.0.0.0 --port $PORT
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable edgecdss.service
echo "  service installed + enabled (not started yet)"

echo ""
echo "============================================================"
echo " Setup complete. Next steps:"
echo "   1. nano $APP_DIR/server/.env   (put in the real OPENAI_API_KEY)"
echo "   2. sudo systemctl start edgecdss"
echo "   3. journalctl -u edgecdss -f   (watch it come up)"
echo "   4. curl http://localhost:$PORT/health"
echo "      -> expect: {\"status\": \"healthy\", \"documents\": 0}"
echo "      (0 documents until ChromaDB is restored/re-ingested)"
echo "============================================================"
