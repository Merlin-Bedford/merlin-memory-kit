#!/usr/bin/env bash
# MERLIN MEMORY KIT - qdrant-boot.sh (Linux/macOS)
# Guarded, logged, idempotent vector-store launcher. See qdrant-boot.ps1 for WHY.
#
# Install (systemd --user example, runs at login):
#   mkdir -p ~/.config/systemd/user
#   cat > ~/.config/systemd/user/qdrant.service <<'EOF'
#   [Unit]
#   Description=Vector memory store (Qdrant)
#   [Service]
#   ExecStart=/bin/bash %h/merlin-memory-kit/launchers/qdrant-boot.sh --foreground
#   Restart=on-failure
#   [Install]
#   WantedBy=default.target
#   EOF
#   systemctl --user enable --now qdrant
# Or simply add to your desktop autostart:
#   bash /path/to/merlin-memory-kit/launchers/qdrant-boot.sh
#
# Configure via env: MMK_QDRANT_DIR, MMK_QDRANT_BIN, MMK_QDRANT_PORT, MMK_BOOT_LOG

set -u
DIR="${MMK_QDRANT_DIR:-$(cd "$(dirname "$0")/.." && pwd)/qdrant}"
BIN="${MMK_QDRANT_BIN:-$DIR/qdrant}"
PORT="${MMK_QDRANT_PORT:-6333}"
LOG="${MMK_BOOT_LOG:-$DIR/qdrant-boot.log}"
CFG="$DIR/config.yaml"

log() { printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "$LOG"; }

listening() {
  # bash builtin TCP probe - no external deps
  (exec 3<>/dev/tcp/127.0.0.1/"$PORT") 2>/dev/null && { exec 3>&- 3<&-; return 0; } || return 1
}

mkdir -p "$DIR"
log "--- boot pass ---"

if listening; then log "already listening on $PORT - nothing to do"; exit 0; fi
if [ ! -x "$BIN" ]; then log "MISSING or non-executable $BIN (set MMK_QDRANT_BIN)"; exit 1; fi

if [ "${1:-}" = "--foreground" ]; then
  # systemd mode: let the supervisor handle restart + logging
  log "starting in foreground on $PORT"
  if [ -f "$CFG" ]; then exec "$BIN" --config-path "$CFG"; else exec "$BIN" --storage-path "$DIR/storage"; fi
fi

log "starting vector store on $PORT"
if [ -f "$CFG" ]; then
  ( cd "$DIR" && nohup "$BIN" --config-path "$CFG" >/dev/null 2>&1 & )
else
  ( cd "$DIR" && nohup "$BIN" --storage-path "$DIR/storage" >/dev/null 2>&1 & )
fi

for i in $(seq 0 29); do
  sleep 2
  if listening; then log "UP on $PORT after ~$((i * 2))s"; exit 0; fi
done
log "FAILED to bind $PORT within 60s - recall is DOWN, investigate now"
exit 1
