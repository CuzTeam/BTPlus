import os

PANEL_DIR = os.environ.get("BT_PANEL_DIR", "/www/server/panel")

COM_MOD = os.path.join(PANEL_DIR, "mod", "project", "agent", "comMod.py")
COM_MOD_BAK = COM_MOD + ".bak"

CONFIG_JSON = os.path.join(PANEL_DIR, "data", "agent", "config.json")
CONFIG_JSON_BAK = CONFIG_JSON + ".bak"

PROMPTS_DIR = os.path.join(PANEL_DIR, "mod", "project", "agent", "prompts")
PROMPTS_BAK_DIR = os.path.join(PANEL_DIR, "data", "agent", "prompts_bak")

AES_KEY = b"Z2B87NEAS2BkxTrh"
AES_IV = b"WwadH66EGWpeeTT6"

PATCH_MARKER1 = "# [AI_PATCH] force default_headers"
PATCH_MARKER2 = "# [AI_PATCH] use_config_api_key"
