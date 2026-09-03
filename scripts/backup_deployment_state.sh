#!/usr/bin/env bash
# =============================================================================
# EdgeCDSS — back up the deployment-specific state that is NOT in git
# =============================================================================
# Everything this captures is gitignored or never-committed, on purpose. It is
# state about ONE box and ONE kit: which vials this bag holds and who signed
# for them, which keys this device uses, which tunnel it is. None of it belongs
# in the repo — but today it exists in exactly one place, and losing the device
# loses it.
#
#   bash scripts/backup_deployment_state.sh
#
# Writes ~/edgecdss-deployment-state-<host>-<date>.tar.gz, mode 600.
# Reads only; it never modifies or deletes the live files.
#
# WHAT IT CAPTURES
# ────────────────
#   server/.env                            API keys, access token, paths
#   server/drug_concentrations.json        the signed concentration master list
#   server/drug_concentrations.log.jsonl   the signoff audit trail
#   ~/.cloudflared/                        tunnel credentials + config
#   /etc/systemd/system/edgecdss.service.d/override.conf   restart policy
#
# Anything missing is skipped with a warning rather than failing the run — a
# box that never had a tunnel should still get a usable backup of the rest.
#
# NOT captured, because the repo or a public source already recovers it:
# the unit file itself (jetson_cdss_setup_v2.sh phase 6 writes it), the JTS
# PDFs (scripts/fetch_jts_cpgs.sh), the ChromaDB (server/tools/ingest_jts.py).
# See docs/RECOVERY.md.
#
# RESTORE
# ───────
# On the rebuilt box, after `git clone` and the setup script:
#
#   tar xzf edgecdss-deployment-state-<host>-<date>.tar.gz
#   cd edgecdss-deployment-state
#
#   # 1. API keys and config  ->  <repo>/server/.env
#   cp server/.env                          /path/to/pi-cloud-cdss/server/.env
#   chmod 600                               /path/to/pi-cloud-cdss/server/.env
#
#   # 2. Concentrations + audit log  ->  <repo>/server/
#   #    Check kit_id first: restore these ONLY onto the same physical kit.
#   #    A signature describes the vials in THAT bag. If the kit changed,
#   #    start from server/drug_concentrations.example.json and re-sign.
#   cp server/drug_concentrations.json      /path/to/pi-cloud-cdss/server/
#   cp server/drug_concentrations.log.jsonl /path/to/pi-cloud-cdss/server/
#
#   # 3. Tunnel credentials  ->  ~/.cloudflared/
#   mkdir -p ~/.cloudflared && cp -a cloudflared/. ~/.cloudflared/
#   chmod 700 ~/.cloudflared && chmod 600 ~/.cloudflared/*
#
#   # 4. systemd restart policy  ->  the override directory (needs root)
#   sudo mkdir -p /etc/systemd/system/edgecdss.service.d
#   sudo cp systemd/override.conf /etc/systemd/system/edgecdss.service.d/
#   sudo systemctl daemon-reload && sudo systemctl restart edgecdss
#
# Then verify: `python3 -c "import drug_concentrations as d; print(d.kit_id())"`
# from server/ should name the kit you expect, and the loader should report no
# rejections.
# =============================================================================
set -euo pipefail
umask 077

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(hostname -s 2>/dev/null || echo unknown)-$(date +%Y-%m-%d)"
NAME="edgecdss-deployment-state"
OUT="$HOME/${NAME}-${STAMP}.tar.gz"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
ROOT="$STAGE/$NAME"
mkdir -p "$ROOT"

MANIFEST="$ROOT/MANIFEST.txt"
{
  echo "EdgeCDSS deployment state"
  echo "host:    $(hostname -f 2>/dev/null || hostname 2>/dev/null || echo unknown)"
  echo "created: $(date -Is)"
  echo "repo:    $REPO"
  echo "commit:  $(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo 'not a git checkout')"
  echo
  echo "CONTAINS SECRETS. See the RESTORE section in scripts/backup_deployment_state.sh."
  echo
  echo "files:"
} > "$MANIFEST"

FOUND=0
MISSING=0

take() {  # take <source> <destination-dir-inside-tar> <description>
  local src="$1" dst="$ROOT/$2" desc="$3"
  if [ ! -e "$src" ]; then
    echo "  ⏭️  skipped (not present): $desc — $src"
    echo "  MISSING  $desc  ($src)" >> "$MANIFEST"
    MISSING=$((MISSING + 1))
    return 0
  fi
  if [ ! -r "$src" ]; then
    echo "  ⚠️  skipped (unreadable): $desc — $src"
    echo "  UNREADABLE  $desc  ($src)" >> "$MANIFEST"
    MISSING=$((MISSING + 1))
    return 0
  fi
  mkdir -p "$dst"
  cp -a "$src" "$dst/"
  echo "  ✅ $desc"
  echo "  ok       $desc  ($src)" >> "$MANIFEST"
  FOUND=$((FOUND + 1))
}

echo "EdgeCDSS — backing up deployment state from $REPO"
echo

take "$REPO/server/.env"                            "server"     "API keys and config (.env)"
take "$REPO/server/drug_concentrations.json"        "server"     "concentration master list (signed)"
take "$REPO/server/drug_concentrations.log.jsonl"   "server"     "concentration signoff audit log"

if [ -d "$HOME/.cloudflared" ]; then
  mkdir -p "$ROOT/cloudflared"
  cp -a "$HOME/.cloudflared/." "$ROOT/cloudflared/"
  echo "  ✅ Cloudflare tunnel credentials (~/.cloudflared/)"
  echo "  ok       Cloudflare tunnel credentials  ($HOME/.cloudflared/)" >> "$MANIFEST"
  FOUND=$((FOUND + 1))
else
  echo "  ⏭️  skipped (not present): Cloudflare tunnel credentials — $HOME/.cloudflared/"
  echo "  MISSING  Cloudflare tunnel credentials  ($HOME/.cloudflared/)" >> "$MANIFEST"
  MISSING=$((MISSING + 1))
fi

take "/etc/systemd/system/edgecdss.service.d/override.conf" "systemd" "systemd restart-policy override"

if [ "$FOUND" -eq 0 ]; then
  echo
  echo "❌ Nothing to back up — found none of the expected files."
  echo "   Is $REPO the EdgeCDSS repo root?"
  exit 1
fi

tar czf "$OUT" -C "$STAGE" "$NAME"
chmod 600 "$OUT"

echo
echo "Wrote $OUT"
echo "  $(du -h "$OUT" | cut -f1), mode 600, $FOUND item(s) captured, $MISSING skipped."
cat <<'WARN'

  ⚠️  THIS ARCHIVE CONTAINS SECRETS.
      API keys, the CDSS access token, and Cloudflare tunnel credentials.

      It belongs on the USB stick or in the password-manager vault.
      NEVER attach it to a GitHub release, commit it to the repo, or copy it
      anywhere the repo is published. It is gitignored state precisely because
      it must not travel with the code.

      Restore instructions are in the header of this script, and the file
      layout is mirrored in MANIFEST.txt inside the archive.
WARN
