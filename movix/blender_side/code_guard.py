"""Claude'un Blender'a gönderdiği Python kodunun güvenlik süzgeci.

Kod güvenilmeyen girdi sayılır. Bu süzgeç en iyi çabadır (Python'u tam izole etmez); amaç dosya, komut, ağ ve
Blender ayarlarına erişimi kapatmak ve yalnızca küp/animasyon kodunun geçmesini sağlamaktır.
Blender'dan bağımsızdır (bpy içermez), bu yüzden normal Python'da da test edilir.
"""
from __future__ import annotations

import ast
import builtins

ALLOWED_IMPORTS = {"bpy", "bmesh", "math", "mathutils", "random"}

# Çağrılmasına ya da başvurulmasına izin verilmeyen çıplak adlar.
FORBIDDEN_NAMES = {
    "__import__", "exec", "eval", "compile", "open", "input", "breakpoint", "globals", "locals", "vars",
    "getattr", "setattr", "delattr", "dir", "memoryview", "exit", "quit", "help", "os", "sys", "subprocess",
    "importlib", "builtins", "socket", "shutil", "pathlib", "ctypes", "pickle", "marshal",
}

# Nokta ile erişilemeyen özellik adları (dosya yazma/okuma, Blender ayarları, betik/eklenti, ağ).
FORBIDDEN_ATTRS = {
    "wm", "script", "preferences", "addon_utils", "app", "utils", "libraries", "texts", "text",
    "export_scene", "import_scene", "export_mesh", "import_mesh", "export_anim", "import_anim",
    "export_image", "import_image", "export_shape", "import_shape", "filepath", "filepath_raw", "filename",
    "directory", "save", "save_render", "save_as_mainfile", "save_mainfile", "open_mainfile", "quit_blender",
    "system", "popen", "load", "write", "read", "driver_add", "drivers", "driver_namespace", "register_class",
    "unregister_class", "execute", "run", "path", "environ", "modules", "builtins", "sys", "os",
}

SAFE_BUILTIN_NAMES = [
    "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float", "int", "isinstance", "len", "list", "map",
    "max", "min", "pow", "print", "range", "reversed", "round", "set", "sorted", "str", "sum", "tuple", "zip",
    "True", "False", "None", "ValueError", "TypeError", "Exception", "RuntimeError", "IndexError", "KeyError",
]

MAX_CODE_CHARS = 60000


def check(code: str) -> list[str]:
    """Sorunların listesini döner; boş liste = kod çalıştırılabilir."""
    if not isinstance(code, str):
        return ["Kod metin olmalı."]
    if len(code) > MAX_CODE_CHARS:
        return ["Kod çok uzun (en fazla %d karakter)." % MAX_CODE_CHARS]
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return ["Sözdizimi hatası: satır %s: %s" % (e.lineno, e.msg)]
    problems: list[str] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in ALLOWED_IMPORTS:
                    problems.append("satır %d: '%s' içe aktarılamaz" % (line, a.name))
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS or node.level:
                problems.append("satır %d: '%s' içe aktarılamaz" % (line, node.module))
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES or (node.id.startswith("__") and node.id.endswith("__")):
                problems.append("satır %d: '%s' kullanılamaz" % (line, node.id))
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRS or node.attr.startswith("__"):
                problems.append("satır %d: '.%s' kullanılamaz" % (line, node.attr))
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            problems.append("satır %d: global/nonlocal kullanılamaz" % line)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            low = node.value.lower()
            if node.value.startswith("__") or "../" in node.value or "..\\" in node.value:
                problems.append("satır %d: şüpheli metin" % line)
            elif low[:2] in ("c:", "d:") or low.startswith("/") and len(low) > 1 and low[1] not in " ":
                problems.append("satır %d: dosya yolu kullanılamaz" % line)
    # tekrarları sadeleştir
    seen: set[str] = set()
    out: list[str] = []
    for p in problems:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out[:12]


def safe_builtins(extra_modules: dict) -> dict:
    """exec için kısıtlı builtins: yalnızca güvenli adlar + yalnızca izinli modülleri getiren __import__."""
    table = {n: getattr(builtins, n) for n in SAFE_BUILTIN_NAMES if hasattr(builtins, n)}

    def _import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
        root = name.split(".")[0]
        if root not in ALLOWED_IMPORTS or root not in extra_modules:
            raise ImportError("'%s' içe aktarılamaz" % name)
        return extra_modules[root]

    table["__import__"] = _import
    return table
