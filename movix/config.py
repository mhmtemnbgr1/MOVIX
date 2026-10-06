"""Yollar, sabitler ve Blender/Claude bulma."""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import unicodedata
from pathlib import Path

APP_NAME = "Movix"
ROOT = Path(__file__).resolve().parent.parent
BRIDGE_SCRIPT = ROOT / "movix" / "blender_side" / "bridge.py"
MCP_SCRIPT = ROOT / "movix" / "mcp_server.py"
SERVER_NAME = "movix"

FRAME_SIZE = 256

# Animasyon kutucukları: (anahtar, başlık anahtarı)
# başlıklar i18n.py içinde ("anim_<anahtar>")
ANIMATIONS = [("walk_right", "walk_right"), ("walk_left", "walk_left"), ("idle", "idle")]

MCP_TOOLS = ["blender_run", "blender_preview", "blender_scene_info"]
TOOLS_ALLOWED = ",".join("mcp__%s__%s" % (SERVER_NAME, t) for t in MCP_TOOLS)
TOOLS_DENIED = "Bash,Edit,Write,Read,Glob,Grep,WebFetch,WebSearch,NotebookEdit,Task,TodoWrite,Skill"


def documents_dir() -> Path:
    return Path(os.environ.get("MOVIX_DOCS") or (Path.home() / "Documents"))


def output_root() -> Path:
    p = documents_dir() / "Movix" / "Blender"
    p.mkdir(parents=True, exist_ok=True)
    return p


def settings_path() -> Path:
    return output_root() / "ayarlar.json"


def load_settings() -> dict:
    try:
        return json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(data: dict) -> None:
    settings_path().write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def slug(name: str) -> str:
    """Dosya adı için güvenli ad: Türkçe harfler sadeleşir, yol karakterleri atılır."""
    table = str.maketrans({"ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g", "ç": "c", "Ç": "c", "ö": "o", "Ö": "o", "ü": "u", "Ü": "u"})
    s = unicodedata.normalize("NFKD", str(name).translate(table)).encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40]
    return s or "karakter"


def find_blender() -> str | None:
    cands: list[str] = []
    env = os.environ.get("MOVIX_BLENDER")
    if env:
        cands.append(env)
    saved = load_settings().get("blender")
    if saved:
        cands.append(saved)
    which = shutil.which("blender")
    if which:
        cands.append(which)
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("LOCALAPPDATA", "")):
        if base:
            found = sorted(glob.glob(os.path.join(base, "Blender Foundation", "Blender *", "blender.exe")), reverse=True)
            cands.extend(found)
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def find_claude() -> str | None:
    which = shutil.which("claude")
    if which:
        return which
    for p in (Path.home() / ".local" / "bin" / "claude.exe", Path.home() / ".local" / "bin" / "claude"):
        if p.is_file():
            return str(p)
    return None
