#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python "${ROOT_DIR}/scripts/reorganize_halt_data.py" \
  --halt-root "${ROOT_DIR}/HALT_Data" \
  --output-root "${ROOT_DIR}/out/reorganized" \
  --csv-out "${ROOT_DIR}/out/reorganized/t2_index.csv" \
  --patients A1041373 A1111060 A1111111 A1128977 A1251362 \
  --workers 12 \
  --transfer-mode copy
