"""Which site this run measures (Checkpoint 30). SITE_ID picks sites/<id>.json; FNB Performance is the default."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SID = os.environ.get("SITE_ID", "fnb")
CFG = json.loads((ROOT / "sites" / f"{SID}.json").read_text(encoding="utf-8"))
DATA = ROOT / CFG.get("data_dir", "data")
LANGS = CFG.get("languages", [{"code": "en", "name": "English"}])
MAIN_LANG = LANGS[0]["code"]
OTHER_LANGS = [x for x in LANGS[1:]]
LANG_NAME = {x["code"]: x["name"] for x in LANGS}


def lang_of(lang_attr):
    """'ar-AE' -> 'ar'; unknown -> the main language."""
    code = (lang_attr or "").split("-")[0].lower()
    return code if code in LANG_NAME else MAIN_LANG
