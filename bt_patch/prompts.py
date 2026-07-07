from __future__ import annotations

import os
import shutil


def clean_prompts(prompts_dir: str, backup_dir: str) -> int:
    if not os.path.isdir(prompts_dir):
        return 0

    patched = 0
    for name in os.listdir(prompts_dir):
        if not name.endswith(".md"):
            continue
        filepath = os.path.join(prompts_dir, name)
        if not os.path.isfile(filepath):
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        filtered = [
            line for line in lines
            if not line.startswith("base_url:") and not line.startswith("api_key:")
        ]

        if len(filtered) == len(lines):
            continue

        os.makedirs(backup_dir, exist_ok=True)
        shutil.copy2(filepath, os.path.join(backup_dir, name))

        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(filtered)

        patched += 1

    return patched


def restore_prompts(prompts_dir: str, backup_dir: str) -> int:
    if not os.path.isdir(backup_dir):
        return 0

    restored = 0
    for name in os.listdir(backup_dir):
        if not name.endswith(".md"):
            continue
        src = os.path.join(backup_dir, name)
        dst = os.path.join(prompts_dir, name)
        shutil.copy2(src, dst)
        restored += 1

    shutil.rmtree(backup_dir)
    return restored
