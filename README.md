# BTPlus
Baota Panel AI Patch Script

## Usage
```bash
# Linux Only
curl -fsSL https://raw.githubusercontent.com/CuzTeam/BTPlus/refs/heads/main/scripts/run.sh | bash -s -- apply

# 指定 API 参数（跳过交互）
curl -fsSL https://raw.githubusercontent.com/CuzTeam/BTPlus/refs/heads/main/scripts/run.sh | bash -s -- apply --url https://api.openai.com/v1 --key sk-xxx

# 查看状态
bash scripts/run.sh status

# 恢复官方配置
bash scripts/run.sh revert
```

## 新版适配
- 自动解密加密的 `comMod.py`（AES-128-CBC）
- Patch `chat()` 硬编码的 `api_key`（新版从 `DEFAULT_CONFIG` 改为 `config`）
- Patch `simple_chat()` 的 `api_key` / `base_url` 回退值
- 强制 `default_headers`（原始 BTPlus 逻辑）
- 清理 prompt 模板中硬编码的 `base_url` / `api_key`
- 幂等 patch + AST 语法校验

## Thanks
- [Linux.do](https://linux.do)
- [(Author) Cuz AI](https://ai.cuz-lab.space)
