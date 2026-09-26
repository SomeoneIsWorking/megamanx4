#!/usr/bin/env bash
# probe_cull_run.sh — a headless, silent, budgeted X4 run with the control channel open, for the
# cull census. NOT ./run.sh: this never opens a window and never plays audio. Maintainer probe.
#
# Usage: probe_cull_run.sh <frames> [port]
# Prints the PID so the caller can kill exactly that process, never a name.
set -u
N="${1:-400}"
PORT="${2:-5961}"
ROOT=/home/bhamil/repo/psx/megamanx4
OUT="$ROOT/scratch/cull_probe"
mkdir -p "$OUT" "$ROOT/scratch/screenshots" "$ROOT/scratch/logs"
cd "$ROOT" || exit 1

export PSXPORT_VK_HEADLESS=1 PSXPORT_NOAUDIO=1 PSXPORT_NOPACE=1
export PSXPORT_SETTINGS="$ROOT/psxport_settings.ini"
export PSXPORT_ASSET_DIR=/home/bhamil/repo/psx/psxport
export PSXPORT_NATIVE_FRAMES="$N"
export PSXPORT_LOG_FILE="$OUT/run_f$N.log"
export PSXPORT_WATCHDOG=60
export PSXPORT_DEBUG_SERVER="$PORT"

build/bin/megamanx4_port > "$OUT/run_f$N.out" 2>&1 &
PID=$!
echo "pid=$PID frames=$N port=$PORT log=$OUT/run_f$N.log"
# Give the product time to boot the guest and reach its first frame boundary, then leave it running
# for the census. The caller kills THIS pid.
sleep "${PROBE_CULL_WARMUP:-25}"
if ! kill -0 "$PID" 2>/dev/null; then
  echo "the product exited before the census could attach; see $OUT/run_f$N.out"
  tail -12 "$OUT/run_f$N.out"
  exit 1
fi
echo "alive after warmup"
