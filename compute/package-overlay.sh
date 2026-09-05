#!/usr/bin/env bash
set -euo pipefail

COMPUTE_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT="${1:-$COMPUTE_DIR/hunyuan3d-compute-overlay.tar.gz}"

cd "$COMPUTE_DIR"
tar -czf "$OUTPUT" --files-from compute-release-files.txt
echo "Created compute overlay: $OUTPUT"
