"""Blender içinde çalışan ortak kit (bpy gerekir): sahne, kamera, ışık, önizleme ve 2B kare/sprite sheet çizimi.

Karakteri kuran işlevler real_kit.py içindedir; Claude'un kodu ikisini de çağırabilir. Kamera karakteri +y yönüne bakar kabul eder.
"""
from __future__ import annotations

import json
import math
import os

import bpy

UNIT = 0.1

# Her animasyonun kare aralığı (dahil). Kare 0 = dinlenme pozu (preview için).
ANIMS = {"idle": (1, 6), "walk_right": (11, 18), "walk_left": (21, 28)}
ANIM_FPS = {"idle": 6, "walk_right": 8, "walk_left": 8}
REST_FRAME = 0
CAM_ELEVATION = 14.0  # derece: hafif yukarıdan bakış küp hacmini gösterir
CAM_ROT = {"front": 180.0, "back": 0.0, "side": 90.0, "three_quarter": 135.0}
OUT_DIR = [os.path.join(os.path.expanduser("~"), "Movix_blender_out")]  # bridge ayarlar

# --- Sahne ---------------------------------------------------------------------------------

def _scene():
    return bpy.context.scene


def _height_units() -> float:
    return float(_scene().get("movix_height", 24)) * UNIT


def _link(obj) -> None:
    _scene().collection.objects.link(obj)


def _root():
    root = bpy.data.objects.get("MovixRoot")
    if root is None:
        root = bpy.data.objects.new("MovixRoot", None)
        _link(root)
    return root


def _ensure_lighting() -> None:
    """Kameraya bağlı güneş + yumuşak dünya ışığı: her açıdan tutarlı aydınlatma."""
    sc = _scene()
    rig = bpy.data.objects.get("MovixCamRig")
    sun_obj = bpy.data.objects.get("MovixSun")
    if sun_obj is None:
        sun = bpy.data.lights.new("MovixSun", "SUN")
        sun_obj = bpy.data.objects.new("MovixSun", sun)
        _link(sun_obj)
    sun_obj.data.energy = 3.2
    sun_obj.data.angle = math.radians(12)  # yumuşak gölge kenarı
    if rig is not None and sun_obj.parent is None:
        sun_obj.parent = rig
    sun_obj.location = (0, 0, 0)
    sun_obj.rotation_euler = (math.radians(52), 0, math.radians(-32))
    world = bpy.data.worlds.get("MovixWorld")
    if world is None:
        world = bpy.data.worlds.new("MovixWorld")
        world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs[0].default_value = (0.82, 0.87, 0.96, 1.0)
        bg.inputs[1].default_value = 0.85
    sc.world = world


def _setup_render(size: int) -> None:
    sc = _scene()
    engine = None
    for name in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH"):
        try:
            sc.render.engine = name
            engine = name
            break
        except TypeError:
            continue
    sc.render.resolution_x = size
    sc.render.resolution_y = size
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    if engine != "BLENDER_WORKBENCH":
        for attr, val in (("taa_render_samples", 32), ("use_shadows", True), ("use_raytracing", False)):
            try:
                setattr(sc.eevee, attr, val)
            except (AttributeError, TypeError):
                pass
    else:
        sc.display.render_aa = "8"
        sh = sc.display.shading
        sh.light = "STUDIO"
        sh.color_type = "MATERIAL"
        sh.show_cavity = True
        sh.show_object_outline = False
        sh.show_specular_highlight = False
        sh.show_shadows = True
        sh.shadow_intensity = 0.45
    try:
        bpy.context.preferences.view.render_display_type = "NONE"  # render penceresi açılmasın
    except Exception:
        pass


def _setup_camera() -> None:
    sc = _scene()
    h = _height_units()
    rig = bpy.data.objects.get("MovixCamRig")
    if rig is None:
        rig = bpy.data.objects.new("MovixCamRig", None)
        _link(rig)
    cam_obj = bpy.data.objects.get("MovixCam")
    if cam_obj is None:
        cam = bpy.data.cameras.new("MovixCam")
        cam_obj = bpy.data.objects.new("MovixCam", cam)
        _link(cam_obj)
        cam_obj.parent = rig
        cam_obj.rotation_euler = (math.radians(90), 0, 0)
    cam_obj.data.type = "ORTHO"
    cam_obj.data.ortho_scale = h * 1.32
    cam_obj.data.clip_start = 0.1
    cam_obj.data.clip_end = 200
    cam_obj.location = (0, -30, 0)
    rig.location = (0, 0, h * 0.5)
    rig.rotation_euler = (math.radians(-CAM_ELEVATION), 0, 0)
    sc.camera = cam_obj
    _ensure_lighting()


def reset(height: int = 24) -> int:
    """Sahneyi temizler ve height küp boyunda bir karakter için hazırlar."""
    height = int(height)
    if not 8 <= height <= 96:
        raise ValueError("height 8 ile 96 arasında olmalı")
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.actions, bpy.data.cameras, bpy.data.lights):
        for item in list(coll):
            if coll is bpy.data.objects:
                bpy.data.objects.remove(item, do_unlink=True)
            else:
                coll.remove(item)
    sc = _scene()
    sc["movix_height"] = height
    sc["movix_ready"] = False
    sc.frame_start = 0
    sc.frame_end = 28
    sc.render.fps = 12
    _root()
    _setup_render(256)
    _setup_camera()
    return height


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def scene_info() -> dict:
    sc = _scene()
    extra = {}
    if sc.get("movix_real"):
        import real_kit  # hazır 3B karakter modu
        extra = real_kit.info()
    return {**extra, "animated": bool(sc.get("movix_ready", False)), "animations": {k: list(v) for k, v in ANIMS.items()}}


def animate(**opts) -> dict:
    """Hareketleri kurar (real_kit.animate'e iletilir)."""
    import real_kit
    return real_kit.animate(**opts)


# --- Önizleme ve çıktı ----------------------------------------------------------------------------

def _render_to(path: str, size: int) -> None:
    _setup_render(size)
    _scene().render.filepath = path
    bpy.ops.render.render(write_still=True)


def preview(view: str = "front", size: int = 384, path: str | None = None) -> str:
    """Karakteri dinlenme pozunda verilen açıdan çizer. Döner: PNG yolu."""
    if view not in CAM_ROT:
        raise ValueError("view şunlardan biri olmalı: " + ", ".join(CAM_ROT))
    size = max(64, min(1024, int(size)))
    _setup_camera()
    rig = bpy.data.objects["MovixCamRig"]
    sc = _scene()
    keep = sc.frame_current
    sc.frame_set(REST_FRAME)
    rig.rotation_euler = (math.radians(-CAM_ELEVATION), 0, math.radians(CAM_ROT[view]))
    if path is None:
        os.makedirs(OUT_DIR[0], exist_ok=True)
        path = os.path.join(OUT_DIR[0], "preview_%s.png" % view)
    try:
        _render_to(path, size)
    finally:
        rig.rotation_euler = (math.radians(-CAM_ELEVATION), 0, 0)
        sc.frame_set(keep)
    return path


def render_animations(out_dir: str, size: int = 256) -> dict:
    """Üç animasyonu kare kare PNG'ye çizer ve tek sprite sheet (satır = animasyon) üretir."""
    import numpy as np  # Blender ile birlikte gelir

    info = scene_info()
    if not info["animated"]:
        animate()
    size = max(64, min(1024, int(size)))
    frames_dir = os.path.join(out_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    _setup_camera()
    rig = bpy.data.objects["MovixCamRig"]
    rig.rotation_euler = (math.radians(-CAM_ELEVATION), 0, 0)
    sc = _scene()
    result: dict = {"size": size, "anims": {}}
    for anim, (a, b) in ANIMS.items():
        paths = []
        for i, f in enumerate(range(a, b + 1)):
            sc.frame_set(f)
            p = os.path.join(frames_dir, "%s_%02d.png" % (anim, i + 1))
            _render_to(p, size)
            paths.append(p)
        result["anims"][anim] = {"frames": paths, "fps": ANIM_FPS[anim], "loop": True}
    sc.frame_set(REST_FRAME)
    cols = max(len(v["frames"]) for v in result["anims"].values())
    rows = len(ANIMS)
    sheet = np.zeros((rows * size, cols * size, 4), dtype=np.float32)
    for r, anim in enumerate(ANIMS):
        for c, p in enumerate(result["anims"][anim]["frames"]):
            img = bpy.data.images.load(p)
            px = np.empty(size * size * 4, dtype=np.float32)
            img.pixels.foreach_get(px)
            bpy.data.images.remove(img)
            y0 = (rows - 1 - r) * size  # Blender görüntüsünde y=0 alttadır
            sheet[y0:y0 + size, c * size:(c + 1) * size, :] = px.reshape(size, size, 4)
    out = bpy.data.images.new("movix_sheet", cols * size, rows * size, alpha=True)
    out.pixels.foreach_set(sheet.ravel())
    sheet_path = os.path.join(out_dir, "sheet.png")
    out.filepath_raw = sheet_path
    out.file_format = "PNG"
    out.save()
    bpy.data.images.remove(out)
    result["sheet"] = sheet_path
    meta = {"frame_width": size, "frame_height": size,
            "anims": {k: {"row": i, "frames": len(result["anims"][k]["frames"]), "fps": ANIM_FPS[k], "loop": True}
                      for i, k in enumerate(ANIMS)}}
    with open(os.path.join(out_dir, "sheet.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    return result


def save_blend(path: str) -> str:
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    return path


API = {"reset": reset, "animate": animate, "preview": preview, "scene_info": scene_info}
