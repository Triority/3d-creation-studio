#!/usr/bin/env bash
set -euo pipefail

PID_FILE=/media/B/Triority/Hunyuan3D-2.1/hunyuan3d-mv.pid
if [[ ! -f "$PID_FILE" ]]; then
  echo "Hunyuan3D multi-view is not running."
  exit 0
fi

PID=$(cat "$PID_FILE")
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  for _ in {1..10}; do
    kill -0 "$PID" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$PID" 2>/dev/null; then
    kill -9 "$PID"
    sleep 1
  fi
fi
rm -f "$PID_FILE"
echo "Hunyuan3D multi-view stopped."
