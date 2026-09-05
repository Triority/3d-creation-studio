#!/usr/bin/env bash
set -euo pipefail
WEB_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$WEB_DIR")"
export HUNYUAN_WEB_DATA_DIR="${HUNYUAN_WEB_DATA_DIR:-$PROJECT_DIR}"
exec "$PROJECT_DIR/.venv/bin/python" "$WEB_DIR/vue_web.py"
