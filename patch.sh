#!/usr/bin/env bash
# AI 助手自定义 API Patch 脚本
# 用途：将聊天/Agent 模型切换到自定义 OpenAI 兼容 API，Embedding 继续走官方
#
# 用法:
#   patch_api.sh apply  [--url BASE_URL] [--key API_KEY]
#   patch_api.sh revert
#   patch_api.sh status

set -euo pipefail

# ── 路径常量 ──────────────────────────────────────────────────────────────────
readonly PANEL_DIR="/www/server/panel"
readonly COM_MOD="$PANEL_DIR/mod/project/agent/comMod.py"
readonly COM_MOD_BAK="$COM_MOD.bak"
readonly CONFIG_JSON="$PANEL_DIR/data/agent/config.json"
readonly CONFIG_JSON_BAK="$CONFIG_JSON.bak"
readonly PROMPTS_DIR="$PANEL_DIR/mod/project/agent/prompts"
readonly PROMPTS_BAK_DIR="$PANEL_DIR/data/agent/prompts_bak"

readonly PATCH_MARKER="# [AI_PATCH] force default_headers"

# ── 颜色 & 日志 ───────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

_ts()   { date '+%H:%M:%S'; }
log()   { echo -e "[$(_ts)] ${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "[$(_ts)] ${YELLOW}[WARN]${NC}  $*"; }
step()  { echo -e "\n[$(_ts)] ${BLUE}[STEP]${NC}  $*"; }
# error 输出到 stderr，调用方可以用 || exit 1 接管，但 set -e 也会自动终止
error() { echo -e "[$(_ts)] ${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── 临时文件管理 ──────────────────────────────────────────────────────────────
_TMPFILES=()

_make_tmp() {
    local tmp
    tmp=$(mktemp)
    _TMPFILES+=("$tmp")
    echo "$tmp"
}

_cleanup() {
    local f
    for f in "${_TMPFILES[@]+"${_TMPFILES[@]}"}"; do
        [[ -f "$f" ]] && rm -f "$f"
    done
}
trap _cleanup EXIT

# ── patch_commod ──────────────────────────────────────────────────────────────
patch_commod() {
    step "检查 comMod.py patch 状态..."

    [[ -f "$COM_MOD" ]] || error "找不到目标文件: $COM_MOD"

    if grep -qF "$PATCH_MARKER" "$COM_MOD"; then
        log "comMod.py 已包含 patch，跳过"
        return 0
    fi

    if [[ ! -f "$COM_MOD_BAK" ]]; then
        cp "$COM_MOD" "$COM_MOD_BAK"
        log "已备份 comMod.py -> $(basename "$COM_MOD_BAK")"
    fi

    # 将 Python 脚本写入临时文件，避免 marker 内容被 shell 解析
    local py_patch
    py_patch=$(_make_tmp)
    cat > "$py_patch" << 'PYEOF'
import sys

filepath = sys.argv[1]
marker   = sys.argv[2]

with open(filepath, "r", encoding="utf-8") as f:
    lines = f.readlines()

target = "if self.config.get('api_key') == self.DEFAULT_CONFIG['api_key']:"
insert = [
    f"        {marker}\n",
    "        self.config['default_headers']['uid']        = self.DEFAULT_CONFIG['default_headers']['uid']\n",
    "        self.config['default_headers']['access-key'] = self.DEFAULT_CONFIG['default_headers']['access-key']\n",
    "        self.config['default_headers']['appid']      = self.DEFAULT_CONFIG['default_headers']['appid']\n",
    "\n",
]

inserted  = False
new_lines = []
for line in lines:
    if not inserted and target in line:
        new_lines.extend(insert)
        inserted = True
    new_lines.append(line)

if not inserted:
    print(f"[ERROR] 未找到插入目标行: {target!r}", file=sys.stderr)
    sys.exit(1)

with open(filepath, "w", encoding="utf-8") as f:
    f.writelines(new_lines)
PYEOF

    if ! python3 "$py_patch" "$COM_MOD" "$PATCH_MARKER"; then
        cp "$COM_MOD_BAK" "$COM_MOD"
        error "comMod.py patch 失败，已自动还原备份"
    fi

    # 二次校验
    if ! grep -qF "$PATCH_MARKER" "$COM_MOD"; then
        cp "$COM_MOD_BAK" "$COM_MOD"
        error "comMod.py patch 校验失败，已自动还原备份"
    fi

    log "comMod.py patch 成功"

    # 清除 prompt 模板中硬编码的 base_url/api_key（先备份）
    _patch_prompts
}

_patch_prompts() {
    [[ -d "$PROMPTS_DIR" ]] || return 0

    step "清理 prompt 模板中的硬编码 API 配置..."

    local patched=0
    local f
    for f in "$PROMPTS_DIR"/*.md; do
        [[ -f "$f" ]] || continue
        if grep -qE "^(base_url|api_key):" "$f"; then
            mkdir -p "$PROMPTS_BAK_DIR"
            cp "$f" "$PROMPTS_BAK_DIR/$(basename "$f")"
            sed -i '/^base_url:/d; /^api_key:/d' "$f"
            log "已清除并备份: $(basename "$f")"
            patched=$((patched + 1))
        fi
    done

    if [[ "$patched" -eq 0 ]]; then
        log "prompt 模板中未发现硬编码配置"
    fi
}

# ── fetch_models ──────────────────────────────────────────────────────────────
# 结果写入 $out_file（每行一个 model id），避免子 shell 吞掉 error() 的 exit
fetch_models() {
    local base_url="$1"
    local api_key="$2"
    local out_file="$3"

    step "拉取模型列表: ${base_url}/models"

    local resp_body
    resp_body=$(_make_tmp)

    local http_code
    # || true：防止 curl 连接错误在 set -e 下直接终止脚本，由后续 http_code 判断
    http_code=$(curl -sf \
        --connect-timeout 10 \
        --max-time 30 \
        -o "$resp_body" \
        -w "%{http_code}" \
        -H "Authorization: Bearer ${api_key}" \
        "${base_url}/models" 2>/dev/null) || true

    if [[ "$http_code" != "200" ]]; then
        warn "响应体 (前 3 行):"
        head -3 "$resp_body" >&2 || true
        error "拉取模型列表失败 (HTTP ${http_code:-000}，可能是网络超时或 URL 错误)"
    fi

    # 解析并过滤，写入 out_file
    local py_parse
    py_parse=$(_make_tmp)
    cat > "$py_parse" << 'PYEOF'
import sys, json

resp_file = sys.argv[1]
out_file  = sys.argv[2]

with open(resp_file, "r", encoding="utf-8") as f:
    try:
        data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[ERROR] 响应不是合法 JSON: {e}", file=sys.stderr)
        sys.exit(1)

models_raw = data.get("data", data) if isinstance(data, dict) else data
result = []
for m in models_raw:
    mid = m.get("id", m) if isinstance(m, dict) else str(m)
    low = mid.lower()
    if "embed" in low or low.startswith("bge"):
        continue
    result.append(mid)

result.sort()

if not result:
    print("[ERROR] 过滤 embed/bge 后无可用模型", file=sys.stderr)
    sys.exit(1)

with open(out_file, "w", encoding="utf-8") as f:
    f.write("\n".join(result) + "\n")
PYEOF

    python3 "$py_parse" "$resp_body" "$out_file"
    log "获取到 $(wc -l < "$out_file") 个可用模型"
}

# ── write_config ──────────────────────────────────────────────────────────────
write_config() {
    local base_url="$1"
    local api_key="$2"
    local models_file="$3"

    step "写入 config.json..."

    mkdir -p "$(dirname "$CONFIG_JSON")"

    if [[ -f "$CONFIG_JSON" && ! -f "$CONFIG_JSON_BAK" ]]; then
        cp "$CONFIG_JSON" "$CONFIG_JSON_BAK"
        log "已备份 config.json -> $(basename "$CONFIG_JSON_BAK")"
    fi

    # 完全由 Python 构造 JSON，彻底规避 shell 字符串注入
    local py_write
    py_write=$(_make_tmp)
    cat > "$py_write" << 'PYEOF'
import sys, json

models_file = sys.argv[1]
base_url    = sys.argv[2]
api_key     = sys.argv[3]
out_path    = sys.argv[4]

with open(models_file, "r", encoding="utf-8") as f:
    models = [line.strip() for line in f if line.strip()]

config = {
    "api_base_url": base_url,
    "api_key":      api_key,
    "models":       models,
}

with open(out_path, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=4, ensure_ascii=False)
    f.write("\n")

print(f"写入完成: {out_path}，共 {len(models)} 个模型")
PYEOF

    python3 "$py_write" "$models_file" "$base_url" "$api_key" "$CONFIG_JSON"
    log "config.json 写入成功"
}

# ── do_apply ──────────────────────────────────────────────────────────────────
do_apply() {
    local base_url="${ARG_URL:-}"
    local api_key="${ARG_KEY:-}"

    echo ""
    echo "========================================="
    echo "  AI 助手自定义 API 配置"
    echo "========================================="

    if [[ -z "$base_url" ]]; then
        read -rp "请输入 Base URL (如 https://api.openai.com/v1): " base_url
    else
        log "Base URL: $base_url"
    fi
    base_url="${base_url%/}"
    [[ -n "$base_url" ]] || error "Base URL 不能为空"

    if [[ -z "$api_key" ]]; then
        read -rp "请输入 API Key: " api_key
    else
        log "API Key: ${api_key:0:8}..."
    fi
    [[ -n "$api_key" ]] || error "API Key 不能为空"

    local models_file
    models_file=$(_make_tmp)
    fetch_models "$base_url" "$api_key" "$models_file"

    echo ""
    log "可用模型列表（已过滤 embed/bge）："
    echo "─────────────────────────────────"
    local i=1
    while IFS= read -r line; do
        printf "  %2d. %s\n" "$i" "$line"
        i=$((i + 1))
    done < "$models_file"
    echo "─────────────────────────────────"
    echo ""

    read -rp "确认使用以上模型？[Y/n]: " confirm
    if [[ "${confirm:-Y}" =~ ^[Nn] ]]; then
        log "已取消，未作任何修改"
        exit 0
    fi

    patch_commod
    write_config "$base_url" "$api_key" "$models_file"

    echo ""
    log "✓ Patch 完成！聊天模型走自定义 API，Embedding 继续走官方。"
    warn "如需恢复，运行: $0 revert"
}

# ── do_revert ─────────────────────────────────────────────────────────────────
do_revert() {
    step "开始 Revert..."
    local reverted=0

    if [[ -f "$COM_MOD_BAK" ]]; then
        cp "$COM_MOD_BAK" "$COM_MOD"
        rm -f "$COM_MOD_BAK"
        log "comMod.py 已恢复"
        reverted=$((reverted + 1))
    else
        warn "未找到 comMod.py.bak，跳过"
    fi

    if [[ -f "$CONFIG_JSON_BAK" ]]; then
        cp "$CONFIG_JSON_BAK" "$CONFIG_JSON"
        rm -f "$CONFIG_JSON_BAK"
        log "config.json 已恢复为原始版本"
        reverted=$((reverted + 1))
    elif [[ -f "$CONFIG_JSON" ]]; then
        rm -f "$CONFIG_JSON"
        log "config.json 已删除（无备份可还原）"
        reverted=$((reverted + 1))
    fi

    # 还原 prompt 模板
    if [[ -d "$PROMPTS_BAK_DIR" ]]; then
        local restored=0
        local f
        for f in "$PROMPTS_BAK_DIR"/*.md; do
            [[ -f "$f" ]] || continue
            cp "$f" "$PROMPTS_DIR/$(basename "$f")"
            log "已还原模板: $(basename "$f")"
            restored=$((restored + 1))
        done
        if [[ "$restored" -gt 0 ]]; then
            rm -rf "$PROMPTS_BAK_DIR"
            log "prompt 模板全部还原（共 $restored 个）"
            reverted=$((reverted + 1))
        fi
    fi

    if [[ "$reverted" -gt 0 ]]; then
        echo ""
        log "✓ Revert 完成，已恢复为官方 API 配置。"
    else
        warn "未找到任何备份，无需恢复。"
    fi
}

# ── do_status ─────────────────────────────────────────────────────────────────
do_status() {
    echo ""
    echo "========================================="
    echo "  当前 Patch 状态"
    echo "========================================="

    # comMod.py
    if grep -qF "$PATCH_MARKER" "$COM_MOD" 2>/dev/null; then
        log "comMod.py     : ✓ 已 patch"
    else
        warn "comMod.py     : ✗ 未 patch（或文件不存在）"
    fi

    # config.json
    if [[ -f "$CONFIG_JSON" ]]; then
        log "config.json   : 存在"
        python3 - "$CONFIG_JSON" << 'PYEOF'
import sys, json
path = sys.argv[1]
try:
    with open(path) as f:
        c = json.load(f)
    key = str(c.get("api_key", ""))
    print(f"  api_base_url : {c.get('api_base_url', 'N/A')}")
    print(f"  api_key      : {key[:8]}{'...' if len(key) > 8 else ''}")
    models = c.get("models", [])
    print(f"  models ({len(models)})  :")
    for m in models:
        print(f"    - {m}")
except Exception as e:
    print(f"  [WARN] 解析失败: {e}", file=sys.stderr)
PYEOF
    else
        warn "config.json   : 不存在"
    fi

    # prompts 备份
    if [[ -d "$PROMPTS_BAK_DIR" ]]; then
        warn "prompt 模板备份: 存在（$PROMPTS_BAK_DIR）"
    fi

    echo ""
}

# ── 参数解析 ──────────────────────────────────────────────────────────────────
ARG_URL=""
ARG_KEY=""
ACTION=""

usage() {
    cat << 'EOF'
用法:
  patch_api.sh apply  [--url BASE_URL] [--key API_KEY]
  patch_api.sh revert
  patch_api.sh status

命令:
  apply    配置自定义 API（默认）
  revert   恢复为官方 API，还原所有备份
  status   查看当前 patch 状态

选项:
  --url BASE_URL   指定 Base URL（跳过交互输入）
  --key API_KEY    指定 API Key（跳过交互输入）
  -h, --help       显示此帮助
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        apply|revert|status)
            ACTION="$1"; shift ;;
        --url)
            [[ -n "${2:-}" ]] || error "--url 需要一个参数"
            ARG_URL="$2"; shift 2 ;;
        --key)
            [[ -n "${2:-}" ]] || error "--key 需要一个参数"
            ARG_KEY="$2"; shift 2 ;;
        -h|--help)
            usage ;;
        *)
            echo "未知参数: $1" >&2
            usage ;;
    esac
done

case "${ACTION:-apply}" in
    apply)  do_apply  ;;
    revert) do_revert ;;
    status) do_status ;;
esac
