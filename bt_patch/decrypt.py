from __future__ import annotations

import base64
import re

from .constants import AES_IV, AES_KEY


def is_encrypted(filepath: str) -> bool:
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            if re.match(r"^(import |from )", stripped):
                return False
            if not re.match(r"^[A-Za-z0-9+/=]+$", stripped):
                return False
            return True
    return False


def decrypt_file(filepath: str) -> int:
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
    except ImportError:
        raise RuntimeError(
            "缺少 pycryptodome，请先安装: pip3 install pycryptodome"
        )

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append("")
            continue
        try:
            ciphertext = base64.b64decode(stripped)
            if len(ciphertext) % 16 != 0 or len(ciphertext) == 0:
                result.append(stripped)
                continue
            cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
            plaintext = unpad(cipher.decrypt(ciphertext), 16)
            result.append(plaintext.decode("utf-8", errors="replace"))
        except Exception:
            result.append(stripped)

    output = "\n".join(result)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(output)

    return len(result)
