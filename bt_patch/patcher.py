from __future__ import annotations

import ast

from .constants import PATCH_MARKER1, PATCH_MARKER2
from .decrypt import decrypt_file, is_encrypted


def patch_commod(filepath: str) -> list[str]:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    applied: list[str] = []

    if PATCH_MARKER1 in content and PATCH_MARKER2 in content:
        return applied

    if is_encrypted(filepath):
        decrypt_file(filepath)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        applied.append("decrypt")

    if PATCH_MARKER1 not in content:
        content = _patch1_default_headers(content)
        applied.append("force_default_headers")

    if PATCH_MARKER2 not in content:
        content = _patch2_chat_api_key(content)
        applied.append("chat_api_key")

    content = _patch3_simple_chat_fallbacks(content)
    applied.append("simple_chat_fallbacks")

    ast.parse(content)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return applied


def _patch1_default_headers(content: str) -> str:
    target = "if self.config.get('api_key') == self.DEFAULT_CONFIG['api_key']:"
    if target not in content:
        raise ValueError(f"未找到 patch1 目标行: {target!r}")

    insert = [
        f"        {PATCH_MARKER1}\n",
        "        self.config['default_headers']['uid']        = self.DEFAULT_CONFIG['default_headers']['uid']\n",
        "        self.config['default_headers']['access-key'] = self.DEFAULT_CONFIG['default_headers']['access-key']\n",
        "        self.config['default_headers']['appid']      = self.DEFAULT_CONFIG['default_headers']['appid']\n",
        "\n",
    ]

    lines = content.split("\n")
    new_lines: list[str] = []
    inserted = False
    for line in lines:
        if not inserted and target in line:
            new_lines.extend(insert)
            inserted = True
        new_lines.append(line)

    if not inserted:
        raise ValueError("patch1 插入失败")

    return "\n".join(new_lines)


def _patch2_chat_api_key(content: str) -> str:
    target = '"api_key": self.DEFAULT_CONFIG[\'api_key\'],'
    replacement = (
        f'"api_key": self.config.get(\'api_key\', self.DEFAULT_CONFIG[\'api_key\']),'
        f"  {PATCH_MARKER2}"
    )
    if target not in content:
        raise ValueError(f"未找到 patch2 目标行 (chat api_key)")
    return content.replace(target, replacement, 1)


def _patch3_simple_chat_fallbacks(content: str) -> str:
    changed = False

    target_ak = "self.DEFAULT_CONFIG['agent'].get('api_key', '')"
    replace_ak = "self.config.get('api_key', '')"
    if target_ak in content:
        content = content.replace(target_ak, replace_ak)
        changed = True

    target_bu = "self.DEFAULT_CONFIG['agent'].get('base_url', '')"
    replace_bu = "self.config.get('api_base_url', '')"
    if target_bu in content:
        content = content.replace(target_bu, replace_bu)
        changed = True

    if not changed:
        raise ValueError("未找到 patch3 目标 (simple_chat fallbacks)")

    return content


def is_patched(filepath: str) -> bool:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return PATCH_MARKER1 in content and PATCH_MARKER2 in content
    except FileNotFoundError:
        return False
