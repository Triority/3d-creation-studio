#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR=/media/B/Triority/Hunyuan3D-2.1
export HUNYUAN_APP_DIR="$APP_DIR"

service ssh start

# PID files survive container recreation, while all old container processes do not.
rm -f "$DATA_DIR/hunyuan3d.pid" "$DATA_DIR/hunyuan3d-mv.pid" "$DATA_DIR/compute-agent.pid"

"$APP_DIR/start-hunyuan3d.sh"
"$APP_DIR/start-hunyuan3d-mv.sh"
"$APP_DIR/start-compute-agent.sh"

term() {
  "$APP_DIR/stop-compute-agent.sh" || true
  "$APP_DIR/stop-hunyuan3d-mv.sh" || true
  "$APP_DIR/stop-hunyuan3d.sh" || true
  service ssh stop || true
  exit 0
}
trap term TERM INT

while true; do
  sleep 30 &
  wait $!
done
