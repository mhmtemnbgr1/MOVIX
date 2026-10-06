"""Blender içinde çalışan uçtan uca deneme (başsız):
blender -b --factory-startup --python tests/blender_selftest.py -- --no-serve --out KLASOR
Sonucu stdout'a 'SELFTEST_JSON {...}' olarak yazar.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "movix", "blender_side"))
import bridge  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
out = argv[argv.index("--out") + 1]
results = {}


def run(code):
    return bridge._execute("run_code", {"code": code})


results["ping"] = bridge._execute("ping", {})
results["new"] = bridge._execute("new_scene", {"character": "Knight"})

CODE = """
use('Mage_Hat')
remove('Helmet')
remove('Cape')
shift_color('Body', 120, 1.1, 1.0)
tint('Mage_Hat', '#c0392b', 'multiply')
resize('Body', 1.3, 1.2, 1.0)
print(swatches(count=4))
print(replace_color('#aab8be', '#3a7bd5', 0.2, part='Body'))
animate(walk='Walking_B', idle='Idle_B')
"""
results["run"] = run(CODE)
results["bad_part"] = run("use('Yok_Body')")
results["no_add"] = run("add('x', 'box', 'head')")
results["no_add"] = run("add('x', 'box', 'head')")
results["bad_resize"] = run("resize('Body', 3, 1, 1)")
results["bad_color"] = run("tint('Body', 'kirmizi')")
results["bad_character"] = run("new_character('Dragon')")
results["bad_anim"] = run("animate(walk='Moonwalk')")


# süzgeç: yasak kodlar reddedilmeli
results["blocked_os"] = run("import os\nos.system('echo x')")
results["blocked_open"] = run("open('x.txt','w')")
results["blocked_wm"] = run("bpy.ops.wm.quit_blender()")
results["blocked_dunder"] = run("x = ().__class__.__bases__")

prev = bridge._execute("preview", {"view": "front", "size": 256})
results["preview"] = prev
results["preview_exists"] = os.path.exists(prev.get("path", ""))
render = bridge._execute("render_animations", {"out_dir": os.path.join(out, "char"), "size": 128})
results["render_ok"] = render.get("ok")
if render.get("ok"):
    results["frames"] = {k: len(v["frames"]) for k, v in render["anims"].items()}
    results["sheet_exists"] = os.path.exists(render["sheet"])
    results["all_frames_exist"] = all(os.path.exists(p) for v in render["anims"].values() for p in v["frames"])
else:
    results["render_error"] = render.get("error")
results["save"] = bridge._execute("save_blend", {"path": os.path.join(out, "char", "character.blend")})
results["scene"] = bridge._execute("scene_info", {})
print("SELFTEST_JSON " + json.dumps(results))
