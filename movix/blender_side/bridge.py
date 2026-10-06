"""Blender'ın içinde çalışan köprü: yerel bir TCP sunucusu açar, gelen komutları Blender'ın ana iş parçacığında çalıştırır.

Başlatma:  blender --factory-startup --python bridge.py -- --port 9876 --token GIZLI --out KLASOR
Protokol:  satır başına bir JSON. İstek {"token", "cmd", "args"}, cevap {"ok", ...}. Yalnızca 127.0.0.1'e bağlanır, token ister.
Komutlar:  ping, new_scene, run_code, preview, scene_info, render_animations, save_blend
"""
from __future__ import annotations

import contextlib
import io
import json
import math
import os
import queue
import socket
import sys
import threading
import traceback

import bpy
import mathutils

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import code_guard  # noqa: E402
import kit  # noqa: E402
import real_kit  # noqa: E402

JOBS: "queue.Queue" = queue.Queue()
MAX_OUTPUT = 4000
MAX_REQUEST = 1_000_000


def _parse_args() -> dict:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"port": 9876, "token": "", "out": os.path.join(os.path.expanduser("~"), "Movix_blender_out")}
    for i, a in enumerate(argv):
        if a == "--port" and i + 1 < len(argv):
            out["port"] = int(argv[i + 1])
        elif a == "--token" and i + 1 < len(argv):
            out["token"] = argv[i + 1]
        elif a == "--out" and i + 1 < len(argv):
            out["out"] = argv[i + 1]
    return out


CFG = _parse_args()
kit.OUT_DIR[0] = CFG["out"]


# --- Komutlar (Blender ana iş parçacığı) ------------------------------------------------------------

def _namespace() -> dict:
    mods = {"bpy": bpy, "math": math, "mathutils": mathutils, "random": __import__("random")}
    try:
        import bmesh
        mods["bmesh"] = bmesh
    except Exception:
        pass
    ns = dict(mods)
    ns.update(kit.API)
    ns.update(real_kit.API)
    ns["Vector"] = mathutils.Vector
    ns["__builtins__"] = code_guard.safe_builtins(mods)
    return ns


def cmd_ping(args: dict) -> dict:
    return {"blender": ".".join(str(v) for v in bpy.app.version), "bridge": 1}


def cmd_new_scene(args: dict) -> dict:
    if args.get("character"):  # hazır 3B karakter (KayKit)
        return real_kit.new_character(str(args["character"]))
    return {"height": kit.reset(int(args.get("height", 24)))}


def cmd_run_code(args: dict) -> dict:
    code = args.get("code", "")
    problems = code_guard.check(code)
    if problems:
        return {"ok": False, "error": "Kod süzgeçten geçmedi:\n- " + "\n- ".join(problems), "output": ""}
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(code, "<claude>", "exec"), _namespace())
    except Exception:
        tb = traceback.format_exc(limit=3)
        return {"ok": False, "error": tb[-MAX_OUTPUT:], "output": buf.getvalue()[-MAX_OUTPUT:]}
    return {"ok": True, "output": buf.getvalue()[-MAX_OUTPUT:], "scene": kit.scene_info()}


def cmd_preview(args: dict) -> dict:
    view = str(args.get("view", "front"))
    size = int(args.get("size", 384))
    return {"path": kit.preview(view, size)}


def cmd_scene_info(args: dict) -> dict:
    return kit.scene_info()


def cmd_render_animations(args: dict) -> dict:
    out_dir = os.path.abspath(str(args["out_dir"]))
    return kit.render_animations(out_dir, int(args.get("size", 256)))


def cmd_save_blend(args: dict) -> dict:
    return {"path": kit.save_blend(os.path.abspath(str(args["path"])))}


COMMANDS = {
    "ping": cmd_ping, "new_scene": cmd_new_scene, "run_code": cmd_run_code, "preview": cmd_preview,
    "scene_info": cmd_scene_info, "render_animations": cmd_render_animations, "save_blend": cmd_save_blend,
}


def _execute(cmd: str, args: dict) -> dict:
    fn = COMMANDS.get(cmd)
    if fn is None:
        return {"ok": False, "error": "bilinmeyen komut: %s" % cmd}
    try:
        res = fn(args if isinstance(args, dict) else {})
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
    if "ok" not in res:
        res["ok"] = True
    return res


def _poll() -> float:
    for _ in range(8):
        try:
            job = JOBS.get_nowait()
        except queue.Empty:
            break
        cmd, args, done, holder = job
        holder["res"] = _execute(cmd, args)
        done.set()
    return 0.05


# --- Sunucu (arka plan iş parçacığı) -----------------------------------------------------------------

def _handle(conn: socket.socket) -> None:
    conn.settimeout(600)
    buf = b""
    try:
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                return
            buf += chunk
            if len(buf) > MAX_REQUEST:
                return
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    req = json.loads(line.decode("utf-8"))
                except ValueError:
                    conn.sendall(b'{"ok": false, "error": "gecersiz json"}\n')
                    continue
                if not isinstance(req, dict) or req.get("token") != CFG["token"] or not CFG["token"]:
                    conn.sendall(b'{"ok": false, "error": "yetkisiz"}\n')
                    return
                done = threading.Event()
                holder: dict = {}
                JOBS.put((str(req.get("cmd", "")), req.get("args", {}), done, holder))
                if not done.wait(900):
                    res = {"ok": False, "error": "Blender zaman aşımı"}
                else:
                    res = holder["res"]
                conn.sendall((json.dumps(res) + "\n").encode("utf-8"))
    except OSError:
        return
    finally:
        conn.close()


def _serve() -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", CFG["port"]))
    srv.listen(8)
    while True:
        conn, _addr = srv.accept()
        threading.Thread(target=_handle, args=(conn,), daemon=True).start()


def start() -> None:
    kit.reset(24)
    bpy.app.timers.register(_poll, persistent=True)
    threading.Thread(target=_serve, daemon=True).start()
    print("[movix] köprü hazır: 127.0.0.1:%d" % CFG["port"])


if "--no-serve" not in sys.argv:
    start()
