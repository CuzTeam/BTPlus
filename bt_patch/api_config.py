from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


def fetch_models(base_url: str, api_key: str) -> list[str]:
    url = base_url.rstrip("/") + "/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"拉取模型列表失败 (HTTP {e.code}): {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"拉取模型列表失败: {e.reason}") from e

    models_raw = data.get("data", data) if isinstance(data, dict) else data
    result: list[str] = []
    for m in models_raw:
        mid = m.get("id", m) if isinstance(m, dict) else str(m)
        low = mid.lower()
        if "embed" in low or low.startswith("bge"):
            continue
        result.append(mid)

    result.sort()
    if not result:
        raise RuntimeError("过滤 embed/bge 后无可用模型")

    return result


def write_config(config_path: str, base_url: str, api_key: str, models: list[str]) -> None:
    os.makedirs(os.path.dirname(config_path), exist_ok=True)

    config = {
        "api_base_url": base_url,
        "api_key": api_key,
        "models": models,
    }

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
        f.write("\n")


def read_config(config_path: str) -> dict | None:
    if not os.path.isfile(config_path):
        return None
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
