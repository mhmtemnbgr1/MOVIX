"""Blender köprüsüne (bridge.py) bağlanan istemci ve Blender süreç yöneticisi."""
from __future__ import annotations

import json
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

from . import config
from .i18n import t

HOST = "127.0.0.1"


class BlenderError(RuntimeError):
    pass


def free_port() -> int:
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def call(port: int, token: str, cmd: str, args: dict | None = None, timeout: float = 900.0) -> dict:
    """Tek komut gönderir. Bağlantı yoksa BlenderError. Cevap {"ok": bool, ...}."""
    payload = (json.dumps({"token": token, "cmd": cmd, "args": args or {}}) + "\n").encode("utf-8")
    try:
        with socket.create_connection((HOST, port), timeout=5) as s:
            s.settimeout(timeout)
            s.sendall(payload)
            buf = b""
            while b"\n" not in buf:
                chunk = s.recv(65536)
                if not chunk:
                    raise BlenderError(t("bl_closed"))
                buf += chunk
    except (OSError, socket.timeout) as e:
        raise BlenderError(t("bl_connect", e)) from e
    try:
        return json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))
    except ValueError as e:
        raise BlenderError("Blender'dan bozuk cevap geldi") from e


def _hide_windows(pid: int) -> None:
    """Blender kendi penceresini kendisi gösterdiği için, o sürecin görünür pencerelerini gizler (yalnızca Windows)."""
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    proc_t = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visit(hwnd, _lp):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            user32.ShowWindow(hwnd, 0)  # SW_HIDE
        return True

    user32.EnumWindows(proc_t(visit), 0)


class Blender:
    """Açık bir Blender penceresini başlatır ve onunla konuşur."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.port = 0
        self.token = ""
        self.out_dir = config.output_root() / "_onizleme"

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, exe: str, wait_s: float = 90.0) -> None:
        if self.running:
            return
        self.port = free_port()
        self.token = secrets.token_hex(16)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        extra = {}
        if sys.platform == "win32":  # Blender arka planda çalışır, kullanıcı penceresini görmez
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0  # SW_HIDE
            extra = {"startupinfo": si, "creationflags": 0x08000000}  # CREATE_NO_WINDOW
        self.proc = subprocess.Popen(
            [exe, "--factory-startup", "--python", str(config.BRIDGE_SCRIPT), "--",
             "--port", str(self.port), "--token", self.token, "--out", str(self.out_dir)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **extra)
        deadline = time.time() + wait_s
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise BlenderError(t("bl_exited"))
            _hide_windows(self.proc.pid)
            try:
                if call(self.port, self.token, "ping", timeout=5).get("ok"):
                    _hide_windows(self.proc.pid)
                    return
            except BlenderError:
                time.sleep(0.5)
        raise BlenderError(t("bl_timeout", int(wait_s)))

    def stop(self) -> None:
        if self.running:
            self.proc.terminate()
        self.proc = None

    def cmd(self, name: str, args: dict | None = None, timeout: float = 900.0) -> dict:
        res = call(self.port, self.token, name, args, timeout)
        if not res.get("ok"):
            raise BlenderError(str(res.get("error", "bilinmeyen hata")))
        return res

    def open_file(self, exe: str, path: Path) -> None:
        subprocess.Popen([exe, str(path)])
