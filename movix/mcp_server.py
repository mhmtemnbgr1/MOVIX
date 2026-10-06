"""Claude Code'un konuştuğu MCP sunucusu (stdio, JSON-RPC). Araçlar çalışan Blender'a köprü üzerinden iletilir.

Ortam: MOVIX_PORT, MOVIX_TOKEN (uygulama yazar). Yalnızca 3 araç sunar: blender_run, blender_preview, blender_scene_info.
"""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from movix import blender_client  # noqa: E402
from movix.prompts import KIT_REFERENCE  # noqa: E402

PROTOCOL = "2024-11-05"
TOOLS = [
    {
        "name": "blender_run",
        "description": "Runs Python code inside the live Blender to turn a ready-made base character into the requested one (mix its parts, resize, recolour, pick animations). Only these are available: the kit functions "
                       "(new_character, use, remove, resize, scale_all, swatches, replace_color, shift_color, tint, animate, preview, scene_info, catalog), bpy, bmesh, math, mathutils, random. File, OS and network access is blocked. "
                       "Returns printed output or the error. Kit reference:\n" + KIT_REFERENCE,
        "inputSchema": {"type": "object", "properties": {"code": {"type": "string", "description": "Python code"}}, "required": ["code"]},
    },
    {
        "name": "blender_preview",
        "description": "Renders the character in rest pose from the given view and returns the image so you can check your work.",
        "inputSchema": {"type": "object", "properties": {
            "view": {"type": "string", "enum": ["front", "side", "back", "three_quarter"]},
            "size": {"type": "integer", "minimum": 128, "maximum": 768}}, "required": []},
    },
    {
        "name": "blender_scene_info",
        "description": "Returns the parts, pivots and cube counts currently in the Blender scene.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
]


def _text(s: str, error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": s}], "isError": error}


def call_tool(name: str, args: dict) -> dict:
    port = int(os.environ.get("MOVIX_PORT", "0"))
    token = os.environ.get("MOVIX_TOKEN", "")
    try:
        if name == "blender_run":
            res = blender_client.call(port, token, "run_code", {"code": str(args.get("code", ""))})
            if not res.get("ok"):
                return _text("ERROR:\n%s\n%s" % (res.get("error", ""), res.get("output", "")), True)
            sc = res.get("scene", {})
            summary = "OK. Output:\n%s\nCharacter: %s, worn: %s, animated: %s" % (
                res.get("output", "").strip() or "(none)", sc.get("character", ""), json.dumps(sc.get("worn", [])), sc.get("animated"))
            return _text(summary)
        if name == "blender_preview":
            res = blender_client.call(port, token, "preview", {"view": args.get("view", "front"), "size": int(args.get("size", 384))})
            if not res.get("ok"):
                return _text("ERROR: %s" % res.get("error", ""), True)
            data = Path(res["path"]).read_bytes()
            return {"content": [{"type": "text", "text": "Preview (%s view, rest pose)" % args.get("view", "front")},
                                {"type": "image", "data": base64.b64encode(data).decode("ascii"), "mimeType": "image/png"}], "isError": False}
        if name == "blender_scene_info":
            res = blender_client.call(port, token, "scene_info")
            res.pop("ok", None)
            return _text(json.dumps(res, ensure_ascii=False))
    except Exception as e:  # noqa: BLE001
        return _text("Blender error: %s" % e, True)
    return _text("unknown tool", True)


def handle(msg: dict) -> dict | None:
    method = msg.get("method", "")
    rid = msg.get("id")
    if rid is None:
        return None  # bildirimler cevap istemez
    if method == "initialize":
        ver = (msg.get("params") or {}).get("protocolVersion", PROTOCOL)
        result = {"protocolVersion": ver, "capabilities": {"tools": {}}, "serverInfo": {"name": "movix", "version": "2.0"}}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        p = msg.get("params") or {}
        result = call_tool(str(p.get("name", "")), p.get("arguments") or {})
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "method not found"}}
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def main() -> None:
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    for raw in stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw.decode("utf-8"))
        except ValueError:
            continue
        reply = handle(msg) if isinstance(msg, dict) else None
        if reply is not None:
            stdout.write((json.dumps(reply) + "\n").encode("utf-8"))
            stdout.flush()


if __name__ == "__main__":
    main()
