from __future__ import annotations

import argparse
import os
import shutil
import sys

from . import api_config, prompts
from .constants import (
    COM_MOD,
    COM_MOD_BAK,
    CONFIG_JSON,
    CONFIG_JSON_BAK,
    PROMPTS_BAK_DIR,
    PROMPTS_DIR,
    PATCH_MARKER1,
    PATCH_MARKER2,
)
from .patcher import is_patched, patch_commod


# ── helpers ───────────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    print(f"  [INFO]  {msg}")


def _warn(msg: str) -> None:
    print(f"  [WARN]  {msg}", file=sys.stderr)


def _step(msg: str) -> None:
    print(f"\n  [STEP]  {msg}")


def _error(msg: str) -> None:
    print(f"\n  [ERROR] {msg}", file=sys.stderr)
    sys.exit(1)


def _read_tty(prompt: str) -> str:
    if sys.stdin.isatty():
        return input(prompt).strip()
    try:
        with open("/dev/tty", "r") as tty:
            return tty.readline().strip()
    except OSError:
        _error("当前为非交互环境且无法访问 /dev/tty，请通过 --url 和 --key 参数传入配置")


def _backup(filepath: str, backup: str) -> None:
    if not os.path.isfile(backup):
        shutil.copy2(filepath, backup)
        _log(f"已备份 {os.path.basename(filepath)} -> {os.path.basename(backup)}")


# ── apply ─────────────────────────────────────────────────────────────────────

def do_apply(args: argparse.Namespace) -> None:
    base_url: str = args.url or _read_tty("请输入 Base URL (如 https://api.openai.com/v1): ")
    base_url = base_url.rstrip("/")
    if not base_url:
        _error("Base URL 不能为空")

    api_key: str = args.key or _read_tty("请输入 API Key: ")
    if not api_key:
        _error("API Key 不能为空")

    print(f"\n{'=' * 41}")
    print("  AI 助手自定义 API 配置 (新版适配)")
    print(f"{'=' * 41}")
    _log(f"Base URL: {base_url}")
    _log(f"API Key:  {api_key[:8]}...")

    # fetch models
    _step("拉取模型列表...")
    try:
        models = api_config.fetch_models(base_url, api_key)
    except RuntimeError as e:
        _error(str(e))

    _log(f"获取到 {len(models)} 个可用模型:")
    print("  " + "-" * 31)
    for i, m in enumerate(models, 1):
        print(f"    {i:2d}. {m}")
    print("  " + "-" * 31)

    confirm = _read_tty("\n确认使用以上模型？[Y/n]: ")
    if confirm and confirm.lower().startswith("n"):
        _log("已取消，未作任何修改")
        return

    # patch comMod.py
    _step("Patching comMod.py...")
    if not os.path.isfile(COM_MOD):
        _error(f"找不到目标文件: {COM_MOD}")

    if is_patched(COM_MOD):
        _log("comMod.py 已包含 patch，跳过")
    else:
        _backup(COM_MOD, COM_MOD_BAK)
        try:
            applied = patch_commod(COM_MOD)
            for a in applied:
                _log(f"  -> {a}")
            _log("comMod.py patch 成功")
        except Exception as e:
            if os.path.isfile(COM_MOD_BAK):
                shutil.copy2(COM_MOD_BAK, COM_MOD)
            _error(f"comMod.py patch 失败: {e}\n已自动还原备份")

    # clean prompts
    _step("清理 prompt 模板...")
    count = prompts.clean_prompts(PROMPTS_DIR, PROMPTS_BAK_DIR)
    if count > 0:
        _log(f"已清除 {count} 个模板中的硬编码配置")
    else:
        _log("prompt 模板中未发现硬编码配置")

    # write config
    _step("写入 config.json...")
    if os.path.isfile(CONFIG_JSON):
        _backup(CONFIG_JSON, CONFIG_JSON_BAK)
    api_config.write_config(CONFIG_JSON, base_url, api_key, models)
    _log(f"config.json 写入成功 ({len(models)} 个模型)")

    print()
    _log("Patch 完成！聊天模型走自定义 API，Embedding 继续走官方。")
    print()
    _log("已应用的补丁:")
    print("    1. 解密 comMod.py (如需要)")
    print("    2. 强制 default_headers (原始 BTPlus)")
    print("    3. chat() api_key -> config (新版适配)")
    print("    4. simple_chat() api_key/base_url -> config (新版适配)")
    print("    5. 清理 prompt 模板硬编码配置")
    print("    6. 写入 config.json")


# ── revert ────────────────────────────────────────────────────────────────────

def do_revert(_args: argparse.Namespace) -> None:
    _step("开始 Revert...")
    reverted = 0

    if os.path.isfile(COM_MOD_BAK):
        shutil.copy2(COM_MOD_BAK, COM_MOD)
        os.remove(COM_MOD_BAK)
        _log("comMod.py 已恢复")
        reverted += 1
    else:
        _warn("未找到 comMod.py.bak，跳过")

    if os.path.isfile(CONFIG_JSON_BAK):
        shutil.copy2(CONFIG_JSON_BAK, CONFIG_JSON)
        os.remove(CONFIG_JSON_BAK)
        _log("config.json 已恢复为原始版本")
        reverted += 1
    elif os.path.isfile(CONFIG_JSON):
        os.remove(CONFIG_JSON)
        _log("config.json 已删除（无备份可还原）")
        reverted += 1

    if os.path.isdir(PROMPTS_BAK_DIR):
        count = prompts.restore_prompts(PROMPTS_DIR, PROMPTS_BAK_DIR)
        if count > 0:
            _log(f"prompt 模板全部还原（共 {count} 个）")
            reverted += 1

    if reverted > 0:
        print()
        _log("Revert 完成，已恢复为官方 API 配置。")
    else:
        _warn("未找到任何备份，无需恢复。")


# ── status ────────────────────────────────────────────────────────────────────

def do_status(_args: argparse.Namespace) -> None:
    print(f"\n{'=' * 41}")
    print("  当前 Patch 状态")
    print(f"{'=' * 41}")

    if is_patched(COM_MOD):
        _log("comMod.py     : 已 patch")
    else:
        _warn("comMod.py     : 未 patch（或文件不存在）")

    cfg = api_config.read_config(CONFIG_JSON)
    if cfg is not None:
        _log("config.json   : 存在")
        key = str(cfg.get("api_key", ""))
        masked = key[:8] + ("..." if len(key) > 8 else "")
        print(f"    api_base_url : {cfg.get('api_base_url', 'N/A')}")
        print(f"    api_key      : {masked}")
        models = cfg.get("models", [])
        print(f"    models ({len(models)})  :")
        for m in models:
            print(f"      - {m}")
    else:
        _warn("config.json   : 不存在")

    if os.path.isdir(PROMPTS_BAK_DIR):
        _warn(f"prompt 模板备份: 存在 ({PROMPTS_BAK_DIR})")

    print()


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="bt_patch",
        description="宝塔面板 AI 助手自定义 API Patch (新版适配)",
    )
    sub = parser.add_subparsers(dest="action")

    p_apply = sub.add_parser("apply", help="配置自定义 API")
    p_apply.add_argument("--url", default=None, help="Base URL")
    p_apply.add_argument("--key", default=None, help="API Key")

    sub.add_parser("revert", help="恢复为官方 API")
    sub.add_parser("status", help="查看当前 patch 状态")

    args = parser.parse_args()

    if args.action == "apply":
        do_apply(args)
    elif args.action == "revert":
        do_revert(args)
    elif args.action == "status":
        do_status(args)
    else:
        parser.print_help()
