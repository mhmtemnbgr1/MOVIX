"""Claude Code CLI'yi başsız çalıştırır: fikir üretimi (araçsız) ve Blender'da karakter kurma (yalnızca 3 MCP aracı)."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable

from . import config, prompts
from .i18n import t

CANCELLED = "cancelled"  # içsel işaret; arayüz kendi dilinde gösterir
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class ClaudeError(RuntimeError):
    pass


class Cancel:
    """İptal bayrağı + çalışan süreç."""

    def __init__(self) -> None:
        self.event = threading.Event()
        self.proc: subprocess.Popen | None = None

    def set(self) -> None:
        self.event.set()
        if self.proc is not None:
            _kill(self.proc)


def _kill(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":  # alt süreçler (MCP sunucusu) de kapansın
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, creationflags=CREATE_NO_WINDOW)
    else:
        proc.kill()


def _workdir() -> str:
    d = Path(tempfile.gettempdir()) / "movix_claude"
    d.mkdir(exist_ok=True)
    return str(d)


def _run(args: list[str], prompt: str, timeout: float, cancel: Cancel | None, on_line: Callable[[str], None] | None = None, env: dict | None = None,
         stop: Callable[[], bool] | None = None) -> list[str]:
    exe = config.find_claude()
    if not exe:
        raise ClaudeError(t("runner_not_found"))
    proc = subprocess.Popen([exe] + args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", cwd=_workdir(), env=env, creationflags=CREATE_NO_WINDOW)
    if cancel is not None:
        cancel.proc = proc
    lines: "queue.Queue[str | None]" = queue.Queue()

    def reader() -> None:
        assert proc.stdout is not None
        for ln in proc.stdout:
            lines.put(ln)
        lines.put(None)

    threading.Thread(target=reader, daemon=True).start()
    try:
        assert proc.stdin is not None
        proc.stdin.write(prompt)
        proc.stdin.close()
    except OSError:
        pass
    out: list[str] = []
    started = time.time()
    done = False
    while not done:
        if cancel is not None and cancel.event.is_set():
            _kill(proc)
            raise ClaudeError(CANCELLED)
        if time.time() - started > timeout:
            _kill(proc)
            raise ClaudeError(t("runner_timeout", int(timeout / 60)))
        if stop is not None and stop():  # bütçe doldu: hata değil, mevcut sahneyle devam edilir
            _kill(proc)
            break
        try:
            ln = lines.get(timeout=0.2)
        except queue.Empty:
            continue
        if ln is None:
            done = True
        else:
            out.append(ln)
            if on_line is not None:
                on_line(ln)
    proc.wait()
    return out


def extract_json(text: str) -> dict:
    """Metindeki ilk dengeli JSON nesnesini okur (kod çiti ya da ek yazı olsa da)."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start:i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except ValueError:
                        pass
                    break
        start = text.find("{", start + 1)
    raise ClaudeError("Claude'dan okunabilir cevap gelmedi.")


def _idea_list(data) -> list:
    """Cevaptaki fikir listesini bulur: 'ideas' ya da başka bir anahtardaki ya da en dıştaki nesne listesi."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("ideas", "fikirler", "characters", "karakterler", "suggestions", "items"):
            if isinstance(data.get(key), list):
                return data[key]
        for val in data.values():
            if isinstance(val, list) and val and all(isinstance(v, dict) for v in val):
                return val
    return []


def _ideas_from(data) -> list[dict]:
    ideas = []
    for it in _idea_list(data):
        if not isinstance(it, dict):
            continue
        title = str(it.get("title") or it.get("name") or it.get("baslik") or it.get("başlık") or "").strip()
        desc = str(it.get("description") or it.get("desc") or it.get("aciklama") or it.get("açıklama") or it.get("prompt") or "").strip()
        if title and desc:
            ideas.append({"title": title[:60], "description": desc[:600]})
    return ideas


def parse_ideas(text: str) -> list[dict]:
    """Metinden fikirleri okur; nesne ya da dizi biçimini, farklı anahtar adlarını kabul eder (en çok fikir veren yorum seçilir)."""
    candidates = []
    try:
        candidates.append(_ideas_from(extract_json(text)))
    except ClaudeError:
        pass
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end > start:
        try:
            candidates.append(_ideas_from(json.loads(text[start:end + 1])))
        except ValueError:
            pass
    ideas = max(candidates, key=len) if candidates else []
    if not ideas:
        raise ClaudeError(t("runner_no_ideas", text.strip()[:120].replace("\n", " ") or t("runner_empty")))
    return ideas[:3]


def suggest(request: str, cancel: Cancel | None = None) -> list[dict]:
    """İsteğe göre 3 karakter önerisi (araçsız, hızlı). Biçim bozuksa bir kez daha dener."""
    last: Exception | None = None
    for attempt in range(2):
        prompt = prompts.ideas_prompt(request)
        if attempt:
            prompt += "\n\nIMPORTANT: your previous reply could not be parsed. Reply with ONLY the JSON object, nothing else."
        out = _run(["-p", "--tools", "", "--output-format", "json", "--no-session-persistence", "--setting-sources", "project", "--effort", "low"],
                   prompt, 180.0, cancel)
        raw = "".join(out)
        try:
            envelope = json.loads(raw)
            text = str(envelope.get("result", ""))
            if envelope.get("is_error"):
                raise ClaudeError(text or t("runner_error"))
        except ValueError:
            text = raw
        try:
            return parse_ideas(text)
        except ClaudeError as e:
            last = e
            if str(e) == CANCELLED:
                raise
    assert last is not None
    raise last


def mcp_config(port: int, token: str) -> Path:
    """Claude Code'a yalnızca bu oturumun Blender köprüsünü gösteren geçici MCP ayarı."""
    cfg = {"mcpServers": {config.SERVER_NAME: {
        "command": sys.executable, "args": [str(config.MCP_SCRIPT)],
        "env": {"MOVIX_PORT": str(port), "MOVIX_TOKEN": token}}}}
    path = Path(tempfile.gettempdir()) / ("movix_mcp_%d.json" % port)
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


def _progress_from(line: str, state: dict, on_progress: Callable[[str], None]) -> None:
    try:
        ev = json.loads(line)
    except ValueError:
        return
    if ev.get("type") != "assistant":
        return
    for block in (ev.get("message") or {}).get("content", []):
        if isinstance(block, dict) and block.get("type") == "text" and str(block.get("text", "")).strip():
            on_progress("Claude: " + " ".join(str(block["text"]).split())[:300])
            continue
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        name = str(block.get("name", ""))
        if name.endswith("blender_run"):
            state["runs"] = state.get("runs", 0) + 1
            on_progress(t("prog_code", state["runs"]))
        elif name.endswith("blender_preview"):
            state["previews"] = state.get("previews", 0) + 1
            on_progress(t("prog_preview", state["previews"]))
        elif name.endswith("blender_scene_info"):
            state["infos"] = state.get("infos", 0) + 1
            on_progress(t("prog_scene"))


MAX_STEPS = 16      # Claude'un araç çağrısı üst sınırı (kod, önizleme, sahne bilgisi)
MAX_SECONDS = 540.0  # Claude'a verilen süre; dolunca mevcut sahneyle bitirilir


def build(prompt: str, port: int, token: str, on_progress: Callable[[str], None], cancel: Cancel | None = None, effort: str = "medium",
          max_steps: int = MAX_STEPS, max_seconds: float = MAX_SECONDS) -> str:
    """Claude'u Blender araçlarıyla çalıştırır. Adım ya da süre bütçesi dolunca durdurur ve sahneyi olduğu gibi bırakır.
    Döner: Claude'un son (kısa) cevabı ('' olabilir)."""
    cfg = mcp_config(port, token)
    args = ["-p", "--mcp-config", str(cfg), "--strict-mcp-config", "--allowedTools", config.TOOLS_ALLOWED,
            "--disallowedTools", config.TOOLS_DENIED, "--setting-sources", "project", "--permission-mode", "dontAsk",
            "--no-session-persistence", "--effort", effort, "--output-format", "stream-json", "--verbose"]
    state: dict = {}
    final: dict = {}
    started = time.time()

    def steps() -> int:
        return state.get("runs", 0) + state.get("previews", 0) + state.get("infos", 0)

    def on_line(ln: str) -> None:
        _progress_from(ln, state, on_progress)
        try:
            ev = json.loads(ln)
            if ev.get("type") == "result":
                final.update(ev)
        except ValueError:
            pass

    def over_budget() -> bool:
        if final:
            return False
        if steps() >= max_steps or time.time() - started > max_seconds:
            if not state.get("limit"):
                state["limit"] = True
                on_progress(t("limit_reached", steps(), int(time.time() - started)))
            return True
        return False

    try:
        _run(args, prompt, 2400.0, cancel, on_line, stop=over_budget)
    finally:
        try:
            cfg.unlink()
        except OSError:
            pass
    if state.get("limit"):
        return str(final.get("result", "")).strip()
    if not final:
        raise ClaudeError(t("runner_closed"))
    if final.get("is_error"):
        raise ClaudeError(str(final.get("result") or t("runner_error")))
    return str(final.get("result", "")).strip()
