#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR=/media/B/Triority/Hunyuan3D-2.1
PID_FILE="$DATA_DIR/hunyuan3d-mv.pid"
LOG_FILE="$DATA_DIR/hunyuan3d-mv.log"
GPU_FILE="$DATA_DIR/hunyuan3d-mv.gpu"
GPU_INDEX="${HUNYUAN_GPU:-1}"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Hunyuan3D multi-view is already running (PID $(cat "$PID_FILE"))."
  exit 0
fi

cd "$APP_DIR"
export CUDA_VISIBLE_DEVICES="$GPU_INDEX"
export HF_ENDPOINT=https://hf-mirror.com
export HF_HOME="$DATA_DIR/cache/huggingface"
export U2NET_HOME="$DATA_DIR/models/u2net"
export GRADIO_ANALYTICS_ENABLED=False
export PYTHONUNBUFFERED=1
export CUDA_HOME=/usr/local/cuda-11.8
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"
export PYOPENGL_PLATFORM=egl

nohup "$DATA_DIR/venv/bin/python" gradio_app.py \
  --model_path "$DATA_DIR/models/Hunyuan3D-2mv" \
  --subfolder hunyuan3d-dit-v2-mv \
  --texgen_model_path "$DATA_DIR/models/Hunyuan3D-2.1" \
  --host 0.0.0.0 \
  --port 7861 \
  --cache-path "$DATA_DIR/outputs-mv" \
  >>"$LOG_FILE" 2>&1 &

echo $! >"$PID_FILE"
echo "$GPU_INDEX" >"$GPU_FILE"
echo "Started Hunyuan3D multi-view + PBR GLB on GPU $GPU_INDEX (PID $(cat "$PID_FILE")); log: $LOG_FILE"
