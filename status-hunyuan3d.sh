#!/usr/bin/env bash
set -euo pipefail

DATA_DIR=/media/B/Triority/Hunyuan3D-2.1
PID_FILE="$DATA_DIR/hunyuan3d.pid"
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "running pid=$(cat "$PID_FILE") container_url=http://127.0.0.1:7860"
  echo "Access through a trusted network or an SSH tunnel to port 7860."
else
  echo "stopped"
fi
tail -n 20 "$DATA_DIR/hunyuan3d.log" 2>/dev/null || true
