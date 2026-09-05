#!/usr/bin/env bash
set -euo pipefail
PID_FILE=/media/B/Triority/Hunyuan3D-2.1/compute-agent.pid
if [[ -f "$PID_FILE" ]]; then
  PID=$(cat "$PID_FILE")
  kill "$PID" 2>/dev/null || true
  rm -f "$PID_FILE"
fi
