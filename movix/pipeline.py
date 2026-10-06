"""Karakter üretim hattı: Claude -> Blender (küpler) -> animasyon kareleri -> kayıt. Arayüzden bağımsızdır (test edilebilir)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

from . import claude_runner, config, prompts
from .i18n import t
from .blender_client import Blender, BlenderError


def unique_folder(title: str) -> Path:
    base = config.output_root() / config.slug(title)
    p = base
    n = 2
    while p.exists():
        p = Path("%s-%d" % (base, n))
        n += 1
    return p


def read_meta(folder: Path) -> dict | None:
    try:
        return json.loads((folder / "karakter.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def list_characters() -> list[dict]:
    out = []
    root = config.output_root()
    for d in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True) if root.exists() else []:
        if d.is_dir() and not d.name.startswith("_"):
            meta = read_meta(d)
            if meta:
                meta["folder"] = str(d)
                out.append(meta)
    return out


def load_frames(folder: Path) -> dict[str, list[Path]]:
    """Klasördeki animasyon karelerini {animasyon: [png, ...]} olarak verir."""
    result: dict[str, list[Path]] = {}
    frames = Path(folder) / "frames"
    for key, _title in config.ANIMATIONS:
        files = sorted(frames.glob(key + "_*.png"))
        if files:
            result[key] = files
    return result


REQUIRED = ("Head", "Body", "ArmLeft", "ArmRight", "LegLeft", "LegRight")


def _missing(info: dict) -> list[str]:
    text = " ".join(info.get("worn", []))
    return [slot for slot in REQUIRED if slot not in text]


def _ensure_complete(blender: Blender, info: dict, on_progress: Callable[[str], None]) -> dict:
    """Karakterde kafa, gövde, kol ya da bacak eksikse (Claude yarıda kaldıysa) tabandaki parçayı geri koyar; olmazsa hata verir."""
    miss = _missing(info)
    if miss:
        on_progress(t("repairing"))
        base = (info.get("character") or "Knight").replace("Rogue_Hooded", "RogueHooded")
        code = "\n".join("use(%r)" % ("%s_%s" % (base, slot)) for slot in miss)
        blender.cmd("run_code", {"code": code})
        info = blender.cmd("scene_info")
        miss = _missing(info)
    if miss:
        raise BlenderError(t("missing_parts"))
    return info


def make_character(blender: Blender, title: str, concept: str, on_progress: Callable[[str], None],
                   cancel: claude_runner.Cancel | None = None, refine: str | None = None, folder: Path | None = None,
                   effort: str = "medium") -> dict:
    """Karakteri kurar ve çizer. refine verilirse mevcut sahne değiştirilir (folder zorunlu). Döner: meta sözlüğü."""
    if refine:
        if folder is None:
            raise ValueError(t("need_folder"))
        prompt = prompts.refine_prompt(refine)
    else:
        on_progress(t("prep_scene"))
        blender.cmd("new_scene", {"character": "Knight"})
        folder = unique_folder(title)
        prompt = prompts.build_prompt(concept)
    summary = claude_runner.build(prompt, blender.port, blender.token, on_progress, cancel, effort)
    info = blender.cmd("scene_info")
    info = _ensure_complete(blender, info, on_progress)
    if not info.get("animated"):
        on_progress(t("making_anims"))
        blender.cmd("run_code", {"code": "animate()"})
    on_progress(t("rendering"))
    folder.mkdir(parents=True, exist_ok=True)
    blender.cmd("render_animations", {"out_dir": str(folder), "size": config.FRAME_SIZE})
    blender.cmd("save_blend", {"path": str(folder / "karakter.blend")})
    old = read_meta(folder) or {}
    meta = {
        "title": old.get("title") or title, "concept": old.get("concept") or concept, "character": info.get("character", ""),
        "created": old.get("created") or time.strftime("%Y-%m-%d %H:%M"),
        "updated": time.strftime("%Y-%m-%d %H:%M"), "summary": summary,
    }
    (folder / "karakter.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    meta["folder"] = str(folder)
    return meta
