#!/usr/bin/env bash
# BTPlus Patch — 宝塔面板 AI 助手自定义 API Patch
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/.../scripts/run.sh | bash
#   bash scripts/run.sh apply --url https://api.openai.com/v1 --key sk-xxx
#   bash scripts/run.sh status
#   bash scripts/run.sh revert
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# ── Python ────────────────────────────────────────────────────────────────────
PYTHON=""
for candidate in python3 python /usr/bin/python3 /usr/bin/python; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done

if [[ -z "$PYTHON" ]]; then
    echo "[ERROR] 未找到 Python，请安装 Python 3" >&2
    exit 1
fi

# ── Run ───────────────────────────────────────────────────────────────────────
exec "$PYTHON" -m bt_patch "$@"
