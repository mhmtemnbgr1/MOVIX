"""README görsellerini üretir (Claude çağırmaz, API kullanmaz): python docs/make_images.py

1) Başsız Blender, hazır karakterleri ve birkaç karıştırma/boyama örneğini çizer (kare kare PNG).
2) Pillow (pip install pillow) bunları GIF, karakter dizisi ve sprite sheet olarak docs/img altında birleştirir.
Yalnızca README için gereklidir; uygulamanın kendisi Pillow istemez.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import bpy  # noqa: F401
    IN_BLENDER = True
except ImportError:
    IN_BLENDER = False

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
IMG = HERE / "img"
SIZE = 256
BG = (231, 236, 245, 255)

BASE = [  # ad, başlık, yürüyüş, bekleme
    ("knight", "Knight", "Walking_A", "Idle_A"),
    ("barbarian", "Barbarian", "Walking_B", "Idle_A"),
    ("mage", "Mage", "Walking_C", "Idle_B"),
    ("ranger", "Ranger", "Walking_A", "Idle_A"),
    ("rogue", "Rogue", "Sneaking", "Idle_A"),
    ("rogue_hooded", "Rogue Hooded", "Sneaking", "Idle_B"),
]
MIX = [  # ad, başlık, kod
    ("celik_sovalye", "Mavi çelik şövalye", "new_character('Knight')\nremove('Helmet')\nuse('Rogue_Head')\n"
     "for p in ('Body', 'ArmLeft', 'ArmRight', 'LegLeft', 'LegRight'):\n    tint(p, '#7fb0ff', 'multiply')\ntint('Cape', '#5b8cff', 'multiply')\n"
     "animate(walk='Walking_B', idle='Idle_A')"),
    ("mor_korucu", "Mor korucu", "new_character('Ranger')\nfor p in ('Body', 'ArmLeft', 'ArmRight', 'LegLeft', 'LegRight', 'Cape'):\n    shift_color(p, 150)\n"
     "animate(walk='Running_A', idle='Idle_B')"),
    ("buyucu_barbar", "Sakallı büyücü", "new_character('Mage')\nfor p in ('Body', 'ArmLeft', 'ArmRight', 'Cape'):\n    shift_color(p, 150, 1.0, 1.1)\n"
     "use('Barbarian_Head')\nanimate(walk='Walking_C', idle='Idle_A')"),
    ('kizil_sovalye', 'Kızıl şövalye', "new_character('Knight')\nremove('Helmet')\nuse('Ranger_Head')\nfor p in ('Body', 'ArmLeft', 'ArmRight', 'LegLeft', 'LegRight'):\n    tint(p, '#ff7a6b', 'multiply')\ntint('Cape', '#ff4d4d', 'multiply')\nanimate(walk='Walking_A', idle='Idle_B')"),
    ('yesil_buyucu', 'Yeşil büyücü', "new_character('Mage')\nfor p in ('Body', 'ArmLeft', 'ArmRight', 'Hat', 'Cape'):\n    shift_color(p, 95, 1.1, 1.0)\nanimate(walk='Walking_C', idle='Idle_A')"),
    ('sisman_manav', 'Şişman manav', "new_character('Ranger')\nresize('Body', 1.5, 1.4, 1.0)\nresize('Head', 1.15, 1.15, 1.15)\nreplace_color('#f8ccab', '#8d5a3b', 0.2)\nanimate(walk='Walking_C', idle='Idle_A')"),
    ("buz_barbar", "Buz barbar", "new_character('Barbarian')\nfor p in ('Body', 'ArmLeft', 'ArmRight', 'LegLeft', 'LegRight'):\n    shift_color(p, 170, 1.2)\n"
     "animate(walk='Walking_A', idle='Idle_B')"),
]


def render_in_blender(tmp: str) -> None:
    sys.path.insert(0, str(ROOT / "movix" / "blender_side"))
    sys.argv += ["--no-serve"]
    import bridge  # noqa: PLC0415

    jobs = [(n, "new_character('%s')\nanimate(walk='%s', idle='%s')" % (t.replace(" ", "_"), w, i)) for n, t, w, i in BASE]
    jobs += [(n, code) for n, _t, code in MIX]
    for name, code in jobs:
        res = bridge._execute("run_code", {"code": code})
        if not res.get("ok"):
            raise SystemExit("%s: %s" % (name, res.get("error")))
        out = bridge._execute("render_animations", {"out_dir": os.path.join(tmp, name), "size": SIZE})
        if not out.get("ok"):
            raise SystemExit("%s çizilemedi: %s" % (name, out.get("error")))
    print("RENDER_DONE")


def font(size: int):
    from PIL import ImageFont
    for p in ("C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/segoeui.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def frame(tmp: str, name: str, anim: str, i: int):
    from PIL import Image
    im = Image.open(os.path.join(tmp, name, "frames", "%s_%02d.png" % (anim, i))).convert("RGBA")
    bg = Image.new("RGBA", im.size, BG)
    bg.alpha_composite(im)
    return bg


def row(tmp: str, items: list, path: Path, scale: float = 0.8) -> None:
    from PIL import Image, ImageDraw
    s = int(SIZE * scale)
    w = len(items) * s
    img = Image.new("RGBA", (w, s + 44), BG)
    d = ImageDraw.Draw(img)
    f = font(20)
    for k, (name, title) in enumerate(items):
        fr = frame(tmp, name, "idle", 1).resize((s, s))
        img.alpha_composite(fr, (k * s, 0))
        tw = d.textlength(title, font=f)
        d.text((k * s + (s - tw) / 2, s + 8), title, fill=(40, 52, 80, 255), font=f)
    img.convert("RGB").save(path, optimize=True)


def gif(tmp: str, name: str, anim: str, path: Path, ms: int) -> None:
    frames = []
    i = 1
    while os.path.exists(os.path.join(tmp, name, "frames", "%s_%02d.png" % (anim, i))):
        frames.append(frame(tmp, name, anim, i).convert("P", palette=1, colors=96))
        i += 1
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=ms, loop=0, optimize=True, disposal=2)


def lineup_gif(tmp: str, path: Path, scale: float = 0.62) -> None:
    """Altı karakter yan yana yürür: README'nin vitrin görseli."""
    from PIL import Image
    s = int(SIZE * scale)
    frames = []
    for i in range(1, 9):
        img = Image.new("RGBA", (s * len(BASE), s), BG)
        for k, (n, _t, _w, _i) in enumerate(BASE):
            img.alpha_composite(frame(tmp, n, "walk_right", i).resize((s, s), Image.LANCZOS), (k * s, 0))
        frames.append(img.convert("P", palette=1, colors=128))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=110, loop=0, optimize=True, disposal=2)


def compose(tmp: str) -> None:
    from PIL import Image
    IMG.mkdir(parents=True, exist_ok=True)
    lineup_gif(tmp, IMG / "hepsi_yuru.gif")
    row(tmp, [(n, t) for n, t, _w, _i in BASE], IMG / "karakterler.png", 0.8)
    row(tmp, [(n, t) for n, t, _c in MIX], IMG / "karistir_boya.png", 1.0)
    for n, _t, _w, _i in BASE:
        gif(tmp, n, "walk_right", IMG / ("%s_yuru.gif" % n), 110)
    for n, _t, _c in MIX:
        gif(tmp, n, "walk_right", IMG / ("%s_yuru.gif" % n), 110)
    gif(tmp, "celik_sovalye", "walk_left", IMG / "celik_sovalye_yuru_sol.gif", 110)
    gif(tmp, "celik_sovalye", "idle", IMG / "celik_sovalye_dur.gif", 170)
    sheet = Image.open(os.path.join(tmp, "celik_sovalye", "sheet.png")).convert("RGBA")
    bg = Image.new("RGBA", sheet.size, BG)
    bg.alpha_composite(sheet)
    bg.resize((sheet.width // 2, sheet.height // 2), Image.LANCZOS).convert("RGB").save(IMG / "sprite_sheet.png", optimize=True)
    print("görseller:", sorted(p.name for p in IMG.iterdir()))


def main() -> None:
    if IN_BLENDER:
        render_in_blender(sys.argv[sys.argv.index("--") + 1])
        return
    sys.path.insert(0, str(ROOT))
    from movix import config
    blender = config.find_blender()
    if not blender:
        raise SystemExit("Blender bulunamadı")
    with tempfile.TemporaryDirectory() as tmp:
        p = subprocess.run([blender, "-b", "--factory-startup", "--python", str(Path(__file__).resolve()), "--", tmp],
                           capture_output=True, text=True, timeout=1800)
        if "RENDER_DONE" not in p.stdout:
            raise SystemExit(p.stdout[-1500:] + p.stderr[-1500:])
        compose(tmp)


if __name__ == "__main__":
    main()
