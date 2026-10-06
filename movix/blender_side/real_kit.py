"""Hazır 3B karakter kiti (bpy gerekir): KayKit Adventurers (CC0) karakterleri ve KayKit Character Animations (CC0) hareketleri.

Altı sevimli karakter (Knight, Barbarian, Mage, Ranger, Rogue, Rogue_Hooded) aynı 23 kemikli iskeleti kullanır; bu yüzden parçaları (kafa, gövde, kol, bacak,
pelerin, şapka, kask...) birbirine karıştırılabilir, renkleri kaydırılabilir ve hareketler (idle, yürüme, koşma...) hepsinde aynı çalışır.
Çıktı 2B kare dizileridir (kit.render_animations). Ek aksesuar, elde taşınan eşya ya da çanta yoktur: tasarımı bozuyorlar; yalnızca hazır parçalar karıştırılır, boyanır ve ölçeklenir.
"""
from __future__ import annotations

import glob
import math
import os
import re

import bpy
import mathutils

import kit

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "assets", "kaykit")
CHARACTERS = {"Knight": "Knight", "Barbarian": "Barbarian", "Mage": "Mage", "Ranger": "Ranger", "Rogue": "Rogue", "Rogue_Hooded": "RogueHooded"}
CORE = ("Head", "Body", "ArmLeft", "ArmRight", "LegLeft", "LegRight")
ANIM_FILES = ("General", "MovementBasic", "MovementAdvanced", "Simulation")
ARM_NAME = "MovixArmature"
KINDS = ("part", "extra")
_STATE: dict = {"actions": [], "ranges": {}}


def _scene():
    return bpy.context.scene


def _find(pattern: str) -> str:
    hits = glob.glob(os.path.join(ASSETS, pattern))
    if not hits:
        raise ValueError("varlık dosyası bulunamadı: %s (assets/kaykit klasörünü kontrol et)" % pattern)
    return hits[0]


def _import(path: str) -> list:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def _armature():
    return bpy.data.objects.get(ARM_NAME)


def _char_file(character: str) -> str:
    if character not in CHARACTERS:
        raise ValueError("karakter şunlardan biri olmalı: " + ", ".join(CHARACTERS))
    return _find(r"adventurers\*\Characters\gltf\%s.glb" % character)


def _prefix_to_char(name: str) -> str:
    prefix = name.split("_", 1)[0]
    for char, pre in CHARACTERS.items():
        if pre == prefix:
            return char
    raise ValueError("bilinmeyen parça '%s'. Örnek: Knight_Body, Mage_Hat (scene_info catalog.parts)" % name)


def _meshes():
    return [o for o in bpy.data.objects if o.type == "MESH" and o.get("movix_kind") in KINDS]


def _drop(o) -> None:
    mesh = o.data
    bpy.data.objects.remove(o, do_unlink=True)
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def _slot(name: str) -> str:
    return name.split(".")[0].split("_", 1)[-1]


# --- Katalog -------------------------------------------------------------------------------

def parts_catalog() -> list:
    """Giyilebilir tüm parça adları (her karakterden)."""
    if not _STATE.get("parts"):
        names = []
        for char in CHARACTERS:
            objs = _import(_char_file(char))
            names += [o.name.split(".")[0] for o in objs if o.type == "MESH" and o.vertex_groups]
            for o in objs:
                bpy.data.objects.remove(o, do_unlink=True)
        _STATE["parts"] = sorted(n for n in names if "Quiver" not in n)
    return _STATE["parts"]


def animations() -> list:
    return list(_STATE["actions"])


def _range(action) -> tuple:
    xs = [kp.co.x for fc in action.fcurves for kp in fc.keyframe_points]
    return (min(xs), max(xs)) if xs else tuple(action.frame_range)


def _load_actions() -> None:
    for f in ANIM_FILES:
        for o in _import(_find(r"animations\*\Animations\gltf\Rig_Medium\Rig_Medium_%s.glb" % f)):
            bpy.data.objects.remove(o, do_unlink=True)
    names = []
    for a in bpy.data.actions:
        if a.name.startswith("T-Pose") or re.search(r"\.\d{3}$", a.name):
            continue
        a.use_fake_user = True
        _STATE["ranges"][a.name] = _range(a)
        names.append(a.name)
    _STATE["actions"] = sorted(names)


# --- Karakter ------------------------------------------------------------------------------

def _adopt(objs: list, keep_names: set) -> list:
    """İçe aktarılan karakterden yalnızca istenen parçaları ana iskelete bağlar; gerisini siler."""
    rig = _armature()
    parts = []
    for o in list(objs):
        base_name = o.name.split(".")[0]
        if o.type == "MESH" and o.vertex_groups and base_name in keep_names:
            old = bpy.data.objects.get(base_name)
            if old is not None and old is not o:
                _drop(old)
            o.name = base_name
            for m in o.modifiers:
                if m.type == "ARMATURE":
                    m.object = rig
            o.parent = rig
            o.matrix_parent_inverse = mathutils.Matrix.Identity(4)
            o["movix_kind"] = "part" if _slot(base_name) in CORE else "extra"
            parts.append(o)
        elif o is not rig:
            bpy.data.objects.remove(o, do_unlink=True)
    return parts


def new_character(character: str = "Knight") -> dict:
    """Sahneyi sıfırlar ve seçilen karakteri (tüm parçalarıyla) yükler, hareketleri kurar. Her zaman ilk çağrı.

    character: Knight, Barbarian, Mage, Ranger, Rogue, Rogue_Hooded
    """
    path = _char_file(character)
    kit.reset(14)
    sc = _scene()
    sc["movix_real"] = True
    sc["movix_character"] = character
    objs = _import(path)
    arm = next(o for o in objs if o.type == "ARMATURE")
    arm.name = ARM_NAME
    for o in list(objs):
        if o.type == "MESH" and not o.vertex_groups:
            bpy.data.objects.remove(o, do_unlink=True)
    root = kit._root()
    arm.parent = root
    arm.rotation_mode = "XYZ"
    root.rotation_mode = "XYZ"
    root.rotation_euler = (0.0, 0.0, math.pi)  # karakter -y'ye bakar; kit +y'yi ön kabul eder
    for o in [o for o in bpy.data.objects if o.parent is arm and o.type == "MESH"]:
        if "Quiver" in o.name:  # sırtta taşınan ek nesne: tasarımı bozduğu için hiç yüklenmez
            _drop(o)
            continue
        o["movix_kind"] = "part" if _slot(o.name) in CORE else "extra"
    _load_actions()
    animate()
    _frame_camera()
    return info()


def _frame_camera() -> None:
    """Kamerayı karakterin (şapka, kask dahil) boyuna göre ayarlar."""
    sc = _scene()
    sc.frame_set(kit.REST_FRAME)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    top = 0.5
    for o in _meshes():
        ev = o.evaluated_get(dg)
        mesh = ev.to_mesh()
        try:
            mw = ev.matrix_world
            top = max([top] + [(mw @ v.co).z for v in mesh.vertices])
        finally:
            ev.to_mesh_clear()
    sc["movix_height"] = max(8, min(30, math.ceil(top / kit.UNIT * 1.0)))
    kit._setup_camera()


def use(part: str) -> str:
    """Bir parçayı giydirir ya da aynı konumdakini onunla değiştirir. Ad: '<Karakter>_<Parça>', örn. 'Mage_Hat', 'Knight_Body', 'Ranger_Head'.

    Aynı iskeleti kullandıkları için parçalar karakterler arasında karıştırılır (Knight gövdesi + Mage kafası + Barbarian kolları...).
    Kafa/gövde/kol/bacak aynı konumdakini değiştirir; şapka, kask, pelerin gibi ekler eklenir (kaldırmak için remove()).
    """
    char = _prefix_to_char(part)
    objs = _import(_char_file(char))
    if part not in {o.name.split(".")[0] for o in objs if o.type == "MESH"}:
        for o in objs:
            bpy.data.objects.remove(o, do_unlink=True)
        raise ValueError("parça '%s' yok. Seçenekler: %s" % (part, ", ".join(parts_catalog())))
    slot = _slot(part)
    if slot in CORE:  # aynı konumdaki çekirdek parçayı (başka karakterden olabilir) çıkar
        for o in [o for o in _meshes() if _slot(o.name) == slot and o.name.split(".")[0] != part]:
            _drop(o)
    _adopt(objs, {part})
    _scene()["movix_ready"] = False
    _frame_camera()
    return part


def remove(name: str) -> int:
    """Giyili bir parçayı çıkarır (örn. 'Knight_Helmet', 'Mage_Cape'); adın bir bölümü de olur ('Cape' hepsini çıkarır). Döner: çıkarılan sayı."""
    hits = [o for o in _meshes() if name in o.name]
    for o in hits:
        _drop(o)
    _scene()["movix_ready"] = False
    _frame_camera()
    return len(hits)


# --- Renk ---------------------------------------------------------------------------------

def _rgba(color: str) -> tuple:
    m = re.match(r"^#?([0-9a-fA-F]{6})$", str(color))
    if not m:
        raise ValueError("renk '#rrggbb' biçiminde olmalı: %r" % (color,))
    h = m.group(1)
    return tuple(kit._srgb_to_linear(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4)) + (1.0,)


def _targets(target: str) -> list:
    t = target.lower()
    if t in ("all", "hepsi"):
        return _meshes()
    return [o for o in _meshes() if t == o.name.lower() or t in o.name.lower()]


def _own_materials(o) -> list:
    """Parçaya özel malzeme kopyaları döndürür (paylaşılan paleti bozmamak için)."""
    mats = []
    for i, mat in enumerate(o.data.materials):
        if mat is None or not mat.use_nodes:
            continue
        if not mat.name.endswith("_mx"):
            mat = mat.copy()
            mat.name = "%s_%d_mx" % (o.name, i)
            o.data.materials[i] = mat
        mats.append(mat)
    return mats


def _splice(nt, bsdf, node_type: str, name: str):
    """Doku ile BSDF 'Base Color' arasına bir düğüm yerleştirir (varsa onu döndürür)."""
    node = nt.nodes.get(name)
    if node is not None:
        return node
    node = nt.nodes.new(node_type)
    node.name = name
    sock = bsdf.inputs["Base Color"]
    src_in = node.inputs["Color"] if "Color" in node.inputs else node.inputs["Color1"]
    if sock.links:
        src = sock.links[0].from_socket
        nt.links.remove(sock.links[0])
        nt.links.new(src, src_in)
    else:
        src_in.default_value = sock.default_value
    nt.links.new(node.outputs["Color"], sock)
    return node


def shift_color(target: str, hue: float = 0.0, saturation: float = 1.0, brightness: float = 1.0) -> int:
    """Parçanın dokusunu bozmadan rengini kaydırır. hue: -180..180 derece (kırmızı->yeşil ~ +120), saturation 0..2, brightness 0..2.

    target: parça adı ya da bir kısmı ('Body', 'Mage_Cape', 'Cape', 'Head'), ya da 'all'. Döner: etkilenen parça sayısı.
    """
    n = 0
    for o in _targets(target):
        for mat in _own_materials(o):
            nt = mat.node_tree
            bsdf = next((x for x in nt.nodes if x.type == "BSDF_PRINCIPLED"), None)
            if bsdf is None:
                continue
            node = _splice(nt, bsdf, "ShaderNodeHueSaturation", "mx_hsv")
            node.inputs["Hue"].default_value = (0.5 + float(hue) / 360.0) % 1.0
            node.inputs["Saturation"].default_value = float(saturation)
            node.inputs["Value"].default_value = float(brightness)
            n += 1
    return n


def tint(target: str, color: str, mode: str = "multiply") -> int:
    """Parçayı belirli bir renge boyar. mode 'multiply': dokuyu renkle çarpar (detay kalır, koyulaşır); 'flat': düz tek renk (tüm detay kaybolur)."""
    if mode not in ("multiply", "flat"):
        raise ValueError("mode 'multiply' ya da 'flat' olmalı")
    rgba = _rgba(color)
    n = 0
    for o in _targets(target):
        for mat in _own_materials(o):
            nt = mat.node_tree
            bsdf = next((x for x in nt.nodes if x.type == "BSDF_PRINCIPLED"), None)
            if bsdf is None:
                continue
            node = _splice(nt, bsdf, "ShaderNodeMixRGB", "mx_tint")
            node.blend_type = "MULTIPLY" if mode == "multiply" else "MIX"
            node.inputs["Fac"].default_value = 1.0
            node.inputs["Color2"].default_value = rgba
            n += 1
    return n


# --- Oran ve doku renkleri -------------------------------------------------------

PIVOT_BONE = (("Head", "head"), ("Helmet", "head"), ("Hat", "head"), ("Mask", "head"), ("ArmLeft", "upperarm.l"), ("ArmRight", "upperarm.r"),
              ("LegLeft", "upperleg.l"), ("LegRight", "upperleg.r"), ("Body", "hips"), ("Cape", "chest"), ("Quiver", "chest"))


def resize(part: str, x: float = 1.0, y: float = 1.0, z: float = 1.0) -> int:
    """Bir parçanın oranını değiştirir (şişman, zayıf, iri kafa, uzun bacak...). x = genişlik, y = derinlik, z = boy; 0.5 ile 1.8 arası.
    Parça kendi eklem noktası çevresinde ölçeklenir (kafa boyundan, kol omuzdan, bacak kalçadan). Aksesuarları EKLEMEDEN önce yap.
    part: parça adı ya da bir kısmı ('Head', 'Body', 'Knight_ArmLeft'). Döner: etkilenen parça sayısı."""
    if not all(0.5 <= float(v) <= 1.8 for v in (x, y, z)):
        raise ValueError("ölçek 0.5 ile 1.8 arasında olmalı")
    rig = _armature()
    n = 0
    for o in [o for o in _meshes() if part.lower() in o.name.lower()]:
        slot = _slot(o.name)
        bone = next((b for key, b in PIVOT_BONE if key in slot), "hips")
        pivot = rig.data.bones[bone].head_local
        for v in o.data.vertices:
            v.co.x = pivot.x + (v.co.x - pivot.x) * float(x)
            v.co.y = pivot.y + (v.co.y - pivot.y) * float(y)
            v.co.z = pivot.z + (v.co.z - pivot.z) * float(z)
        o.data.update()
        n += 1
    if not n:
        raise ValueError("'%s' adlı parça yok. Giyili parçalar: %s" % (part, ", ".join(sorted(o.name for o in _meshes()))))
    _frame_camera()
    return n


def scale_all(s: float) -> None:
    """Bütün karakteri büyütür ya da küçültür (0.6 ile 1.6 arası)."""
    if not 0.6 <= float(s) <= 1.6:
        raise ValueError("ölçek 0.6 ile 1.6 arasında olmalı")
    kit._root().scale = (float(s),) * 3
    _frame_camera()


def _color_name(r: float, g: float, b: float) -> str:
    mx, mn = max(r, g, b), min(r, g, b)
    v, sat = mx, (mx - mn) / mx if mx else 0.0
    if v < 0.16:
        return "black"
    if sat < 0.12:
        return "white" if v > 0.85 else ("light gray" if v > 0.62 else ("gray" if v > 0.38 else "dark gray"))
    if mx == r:
        h = ((g - b) / (mx - mn)) % 6
    elif mx == g:
        h = (b - r) / (mx - mn) + 2
    else:
        h = (r - g) / (mx - mn) + 4
    h *= 60
    if h < 15 or h >= 345:
        name = "red"
    elif h < 40:
        name = "brown/orange" if v < 0.7 or sat > 0.6 else "skin/tan"
    elif h < 65:
        name = "yellow/gold" if sat > 0.5 else "beige"
    elif h < 160:
        name = "green"
    elif h < 200:
        name = "teal"
    elif h < 255:
        name = "blue"
    elif h < 290:
        name = "purple"
    else:
        name = "pink/magenta"
    return ("dark " if v < 0.4 else ("light " if v > 0.85 and sat < 0.5 else "")) + name


def _texture_nodes(o) -> list:
    return [n for m in o.data.materials if m is not None and m.use_nodes for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image]


def _read_pixels(img):
    import numpy as np
    w, h = img.size
    arr = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(arr)
    return arr.reshape(-1, 4)


def _to_srgb(arr):
    """Blender bayt dokuların 'pixels' değerlerini sRGB kodlu verir; olduğu gibi kullanılır."""
    import numpy as np
    return np.clip(arr, 0.0, 1.0)


def swatches(part: str | None = None, count: int = 16) -> list:
    """Parçanın (verilmezse karakterin) dokusundaki baskın renkleri verir: [{'hex', 'name', 'share'}]. replace_color için hangi rengin neyi boyadığını anlamana yarar."""
    import numpy as np
    objs = [o for o in _meshes() if part is None or part.lower() in o.name.lower()]
    nodes = [n for o in objs for n in _texture_nodes(o)]
    if not nodes:
        raise ValueError("dokulu parça bulunamadı")
    img = nodes[0].image
    px = _to_srgb(_read_pixels(img))
    mask = px[:, 3] > 0.5
    q = np.round(px[mask, :3] * 15).astype(np.int32)
    keys = q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2]
    uniq, inv, cnt = np.unique(keys, return_inverse=True, return_counts=True)
    order = np.argsort(-cnt)[:count]
    total = float(mask.sum())
    out = []
    for i in order:
        sel = px[mask, :3][inv == i].mean(axis=0)
        out.append({"hex": "#%02x%02x%02x" % tuple(int(round(c * 255)) for c in sel), "name": _color_name(*[float(c) for c in sel]), "share": round(cnt[i] / total, 3)})
    return out


def replace_color(old: str, new: str, tolerance: float = 0.16, part: str | None = None) -> int:
    """Dokudaki bir rengi (ve yakın tonlarını, gölge geçişlerini koruyarak) başka bir renkle değiştirir. Saç, ten, kumaş gibi bölgeleri tek tek boyamanın yolu.

    old: swatches() ile bulduğun renk; new: istediğin renk; tolerance: 0.05 (sıkı) - 0.3 (geniş);
    part: verilirse yalnızca o parçada (ona özel doku kopyası açılır), verilmezse bu rengin geçtiği her yerde. Döner: değişen piksel sayısı."""
    import numpy as np
    mo, mn = re.match(r"^#?([0-9a-fA-F]{6})$", str(old)), re.match(r"^#?([0-9a-fA-F]{6})$", str(new))
    if not (mo and mn):
        raise ValueError("renkler '#rrggbb' biçiminde olmalı")
    tol = max(0.02, min(0.4, float(tolerance)))
    c_old = np.array([int(mo.group(1)[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32)
    c_new = np.array([int(mn.group(1)[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32)
    objs = [o for o in _meshes() if part is None or part.lower() in o.name.lower()]
    done, total = set(), 0
    for o in objs:
        for node in _texture_nodes(o):
            img = node.image
            if part is not None and not img.name.endswith("_mine_" + o.name):
                img = img.copy()
                img.name = img.name.split("_mine_")[0] + "_mine_" + o.name
                node.image = img
            if img.name in done:
                continue
            done.add(img.name)
            px = _read_pixels(img)
            srgb = _to_srgb(px)
            dist = np.sqrt(((srgb[:, :3] - c_old) ** 2).sum(axis=1))
            hit = (dist < tol * 1.7320508) & (srgb[:, 3] > 0.5)
            if hit.any():
                lum_old = max(0.05, float(c_old @ [0.2126, 0.7152, 0.0722]))
                lum_px = srgb[hit, :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
                shade = (lum_px / lum_old)[:, None]
                out = np.clip(c_new[None, :] * shade, 0.0, 1.0)
                px[hit, :3] = out
                img.pixels.foreach_set(px.ravel())
                img.update()
                total += int(hit.sum())
    return total


# --- Animasyon ----------------------------------------------------------------------------

def _strip(rig, name: str, action, start: int, frames: int, hold: bool = False):
    track = rig.animation_data.nla_tracks.new()
    track.name = name
    strip = track.strips.new(name, start, action)
    if hasattr(strip, "action_slot") and getattr(action, "slots", None):
        try:
            strip.action_slot = action.slots[0]
        except (TypeError, RuntimeError):
            pass
    a0, a1 = _STATE["ranges"].get(action.name, _range(action))
    strip.action_frame_start = a0
    strip.action_frame_end = a1
    strip.scale = frames / max(1.0, a1 - a0)
    strip.extrapolation = "HOLD" if hold else "NOTHING"
    strip.blend_type = "REPLACE"
    return strip


def animate(walk: str = "Walking_A", idle: str = "Idle_A", **_ignored) -> dict:
    """Üç sprite animasyonunu (idle, walk_right, walk_left) kurar. walk: Walking_A/B/C, Running_A/B, Sneaking...; idle: Idle_A, Idle_B...
    Tüm adlar için scene_info()['catalog']['animations']."""
    rig = _armature()
    if rig is None:
        raise ValueError("önce new_character() çağır")
    acts = {a.name: a for a in bpy.data.actions}
    for label, want in (("walk", walk), ("idle", idle)):
        if want not in acts:
            raise ValueError("bilinmeyen %s hareketi '%s'. Olanlar: %s" % (label, want, ", ".join(_STATE["actions"])))
    rig.animation_data_clear()
    rig.animation_data_create()
    _strip(rig, "rest", acts[idle], 0, 1, hold=True)
    for anim, (a, b) in kit.ANIMS.items():
        _strip(rig, anim, acts[idle if anim == "idle" else walk], a, b - a + 1)
    root = kit._root()
    root.animation_data_clear()
    base = math.pi
    root.rotation_euler = (0.0, 0.0, base)
    root.keyframe_insert(data_path="rotation_euler", frame=kit.REST_FRAME)
    for anim, (a, b) in kit.ANIMS.items():
        deg = {"idle": 180.0, "walk_right": -90.0, "walk_left": 90.0}[anim]
        for f in range(a, b + 1):
            root.rotation_euler = (0.0, 0.0, base + math.radians(deg))
            root.keyframe_insert(data_path="rotation_euler", frame=f)
    try:
        for fc in root.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"
    except Exception:  # noqa: BLE001
        pass
    sc = _scene()
    sc.frame_start, sc.frame_end = 0, 29
    sc.frame_set(kit.REST_FRAME)
    sc["movix_ready"] = True
    sc["movix_walk"] = walk
    sc["movix_idle"] = idle
    return {"animations": {k: list(v) for k, v in kit.ANIMS.items()}, "walk": walk, "idle": idle}


# --- Bilgi --------------------------------------------------------------------------------

def info() -> dict:
    sc = _scene()
    return {"character": sc.get("movix_character", ""), "worn": sorted(o.name for o in _meshes()),
            "walk": sc.get("movix_walk", ""), "idle": sc.get("movix_idle", "")}


def catalog() -> dict:
    return {"characters": list(CHARACTERS), "parts": parts_catalog(), "animations": animations()}


API = {"new_character": new_character, "use": use, "remove": remove, "shift_color": shift_color, "tint": tint, "catalog": catalog,
       "resize": resize, "scale_all": scale_all, "swatches": swatches, "replace_color": replace_color}
