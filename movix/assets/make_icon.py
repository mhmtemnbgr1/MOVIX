"""MV logosunu (icon.png + icon.ico) üretir: python movix/assets/make_icon.py"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent
S = 512
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((0, 0, S - 1, S - 1), radius=110, fill="#171a23")
d.rounded_rectangle((18, 18, S - 19, S - 19), radius=96, outline="#6c8cff", width=14)
font = None
for name in ("seguibl.ttf", "arialbd.ttf", "segoeuib.ttf"):
    try:
        font = ImageFont.truetype(name, 260)
        break
    except OSError:
        pass
font = font or ImageFont.load_default()
d.text((S / 2, S / 2 + 6), "MV", font=font, fill="#e6e8ee", anchor="mm")
d.rectangle((120, 400, 392, 416), fill="#6c8cff")
img.save(OUT / "icon.png")
img.save(OUT / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
