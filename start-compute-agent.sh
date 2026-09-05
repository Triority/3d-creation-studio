#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR=/media/B/Triority/Hunyuan3D-2.1
PID_FILE="$DATA_DIR/compute-agent.pid"
LOG_FILE="$DATA_DIR/compute-agent.log"
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Compute agent already running (PID $(cat "$PID_FILE"))."
  exit 0
fi
cd "$APP_DIR"
export HUNYUAN_APP_DIR="$APP_DIR"
export HUNYUAN_IDLE_TIMEOUT="${HUNYUAN_IDLE_TIMEOUT:-600}"
export HUNYUAN_IDLE_CHECK_INTERVAL="${HUNYUAN_IDLE_CHECK_INTERVAL:-30}"
nohup "$DATA_DIR/venv/bin/uvicorn" compute_agent:api --host 0.0.0.0 --port 7863 >>"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"
echo "Compute agent started on port 7863 (PID $(cat "$PID_FILE")); models load on demand and unload after ${HUNYUAN_IDLE_TIMEOUT}s idle."
