#!/usr/bin/env bash
set -euo pipefail

DATA_DIR=/media/B/Triority/Hunyuan3D-2.1

check_service() {
  local name=$1 pid_file=$2 port=$3
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "$name: running (PID $(cat "$pid_file"), port $port)"
  else
    echo "$name: stopped (port $port)"
  fi
}

check_service "Hunyuan3D-2.1 single/text/PBR" "$DATA_DIR/hunyuan3d.pid" 7860
check_service "Hunyuan3D-2mv multi-view/PBR" "$DATA_DIR/hunyuan3d-mv.pid" 7861
check_service "Unified Web Studio" "$DATA_DIR/hunyuan3d-web.pid" 7862
echo
echo "Recommended access:"
echo "Use an SSH tunnel if these ports are not directly reachable."
echo "Open http://127.0.0.1:7862"
