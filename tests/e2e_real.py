"""Gerçek uçtan uca deneme (Claude hesabını ve Blender'ı kullanır, birkaç dakika sürer):
python tests/e2e_real.py ["istek"]
Blender penceresi açılır; Claude karakteri canlı özelleştirir. Sonuç Documents/Movix/Blender (ya da MOVIX_DOCS) altına yazılır."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from movix import claude_runner, config, pipeline  # noqa: E402
from movix.blender_client import Blender  # noqa: E402

wish = sys.argv[1] if len(sys.argv) > 1 else "yeşil cübbeli neşeli bir büyücü"
t0 = time.time()
print("1) öneriler…", flush=True)
ideas = claude_runner.suggest(wish)
for i in ideas:
    print("  -", i["title"], "|", i["description"], flush=True)
print("   (%.0f sn)" % (time.time() - t0), flush=True)

b = Blender()
b.start(config.find_blender())
print("2) Blender bağlı, karakter kuruluyor:", ideas[0]["title"], flush=True)
t1 = time.time()
meta = pipeline.make_character(b, ideas[0]["title"], ideas[0]["description"], lambda s: print("   ", s, flush=True))
print("3) bitti (%.0f sn):" % (time.time() - t1), meta, flush=True)
b.stop()
