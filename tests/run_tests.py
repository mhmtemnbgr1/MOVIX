"""Testler: python tests/run_tests.py  (Blender kuruluysa başsız Blender denemesi de çalışır; gerçek Claude çağrısı yapmaz)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "movix" / "blender_side"))

from movix import claude_runner, config, i18n, mcp_server, pipeline, prompts  # noqa: E402
import code_guard  # noqa: E402


class TestGuard(unittest.TestCase):
    def test_allows_kit_code(self):
        code = "import math\nnew_character('Knight')\nuse('Mage_Hat')\nshift_color('Body', 120, 1.1, 1.0)\nanimate(walk='Running_A')\n"
        self.assertEqual(code_guard.check(code), [])

    def test_blocks_dangerous(self):
        for bad in ["import os", "from subprocess import run", "open('a','w')", "exec('1')", "eval('1')", "__import__('os')",
                    "getattr(bpy, 'ops')", "bpy.ops.wm.quit_blender()", "bpy.data.libraries.load('x')", "x = ().__class__",
                    "bpy.ops.export_scene.fbx(filepath='C:/x.fbx')", "p = 'C:/Users/a'", "bpy.context.preferences", "global x"]:
            self.assertTrue(code_guard.check(bad), "geçmemeli: " + bad)

    def test_syntax_and_size(self):
        self.assertTrue(code_guard.check("def ("))
        self.assertTrue(code_guard.check("x=1\n" * 40000))

    def test_safe_builtins(self):
        b = code_guard.safe_builtins({"math": object()})
        self.assertNotIn("open", b)
        self.assertNotIn("exec", b)
        with self.assertRaises(ImportError):
            b["__import__"]("os")


class TestRunner(unittest.TestCase):
    def test_extract_json(self):
        self.assertEqual(claude_runner.extract_json('metin ```json\n{"a": {"b": "}"}}\n``` son')["a"]["b"], "}")
        with self.assertRaises(claude_runner.ClaudeError):
            claude_runner.extract_json("hiç json yok")

    def test_parse_ideas(self):
        text = json.dumps({"ideas": [{"title": "A", "description": "x"}, {"title": "B", "description": "y"},
                                      {"title": "", "description": "z"}, {"title": "C", "description": "w"}, {"title": "D", "description": "v"}]})
        ideas = claude_runner.parse_ideas(text)
        self.assertEqual([i["title"] for i in ideas], ["A", "B", "C"])
        with self.assertRaises(claude_runner.ClaudeError):
            claude_runner.parse_ideas('{"ideas": []}')
        alt = claude_runner.parse_ideas('Tabii!\n[{"name": "X", "desc": "y"}, {"title": "Z", "açıklama": "w"}]')
        self.assertEqual([i["title"] for i in alt], ["X", "Z"])
        self.assertEqual(claude_runner.parse_ideas('{"karakterler": [{"title": "K", "description": "d"}]}')[0]["title"], "K")

    def test_progress_lines(self):
        seen: list[str] = []
        state: dict = {}
        ev = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "mcp__movix__blender_run", "input": {}}]}}
        claude_runner._progress_from(json.dumps(ev), state, seen.append)
        ev["message"]["content"][0]["name"] = "mcp__movix__blender_preview"
        claude_runner._progress_from(json.dumps(ev), state, seen.append)
        self.assertEqual(len(seen), 2)
        self.assertIn("1", seen[0])

    def test_mcp_config_only_movix(self):
        p = claude_runner.mcp_config(12345, "tok")
        cfg = json.loads(p.read_text(encoding="utf-8"))
        p.unlink()
        self.assertEqual(list(cfg["mcpServers"]), ["movix"])
        self.assertEqual(cfg["mcpServers"]["movix"]["env"]["MOVIX_PORT"], "12345")
        self.assertNotIn("Bash", config.TOOLS_ALLOWED)
        self.assertEqual(len(config.TOOLS_ALLOWED.split(",")), 3)


class TestI18n(unittest.TestCase):
    def test_same_keys_and_placeholders(self):
        tr, en = i18n.STRINGS["tr"], i18n.STRINGS["en"]
        self.assertEqual(set(tr), set(en), "iki dilde de aynı anahtarlar olmalı")
        for key in tr:
            self.assertEqual(tr[key].count("%s") + tr[key].count("%d"), en[key].count("%s") + en[key].count("%d"), key)

    def test_switch_and_prompts(self):
        try:
            i18n.set_lang("en", persist=False)
            self.assertEqual(i18n.t("cancel"), "✕ Cancel")
            self.assertEqual(i18n.t("prog_code", 3), "Claude is customising the character… (code step 3)")
            self.assertIn("IN ENGLISH", prompts.ideas_prompt("pirate"))
            self.assertIn("English sentence", prompts.build_prompt("pirate"))
            i18n.set_lang("tr", persist=False)
            self.assertEqual(i18n.t("cancel"), "✕ İptal")
            self.assertIn("IN TURKISH", prompts.ideas_prompt("korsan"))
            self.assertIn("Turkish sentence", prompts.refine_prompt("mavi yap"))
            self.assertNotIn("{LANG}", prompts.build_prompt("x"))
            with self.assertRaises(ValueError):
                i18n.set_lang("xx", persist=False)
        finally:
            i18n.set_lang("tr", persist=False)


class TestBudget(unittest.TestCase):
    def test_run_stops_when_budget_is_over(self):
        """Adım/süre bütçesi dolunca süreç öldürülür ve hata vermeden dönülür."""
        import time
        real = config.find_claude
        config.find_claude = lambda: sys.executable
        try:
            code = "import sys,time\nfor i in range(100):\n    print('satir', i, flush=True)\n    time.sleep(0.2)\n"
            seen: list[str] = []
            t0 = time.time()
            out = claude_runner._run(["-c", code], "", 60.0, None, seen.append, stop=lambda: len(seen) >= 3)
            self.assertLess(time.time() - t0, 10)
            self.assertGreaterEqual(len(out), 3)
            self.assertLess(len(out), 20)
        finally:
            config.find_claude = real

    def test_step_counting_includes_scene_info(self):
        state: dict = {}
        ev = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "mcp__movix__blender_scene_info", "input": {}}]}}
        claude_runner._progress_from(json.dumps(ev), state, lambda _m: None)
        self.assertEqual(state.get("infos"), 1)

    def test_missing_parts_detection(self):
        full = ["Knight_Head", "Knight_Body", "Knight_ArmLeft", "Knight_ArmRight", "Knight_LegLeft", "Knight_LegRight"]
        self.assertEqual(pipeline._missing({"worn": full}), [])
        self.assertEqual(pipeline._missing({"worn": [n for n in full if "Head" not in n]}), ["Head"])
        self.assertEqual(pipeline._missing({"worn": []}), list(pipeline.REQUIRED))


class TestPrompts(unittest.TestCase):
    def test_prompts(self):
        self.assertIn("new_character", prompts.KIT_REFERENCE)
        self.assertIn("NO props", prompts.KIT_REFERENCE)
        for tool in ("resize(", "replace_color(", "swatches(", "tint("):
            self.assertIn(tool, prompts.KIT_REFERENCE)
        for gone in ("add(name", "bounds(", "'dome'"):
            self.assertNotIn(gone, prompts.KIT_REFERENCE)
        self.assertIn("robot", prompts.build_prompt("robot"))
        self.assertIn("kırmızı pelerin", prompts.refine_prompt("kırmızı pelerin ekle"))
        self.assertIn("3 ideas", prompts.ideas_prompt("korsan"))

    def test_reference_example_passes_guard(self):
        example = prompts.KIT_REFERENCE.split("EXAMPLE (")[1].split("):\n", 1)[1]
        self.assertEqual(code_guard.check(example), [])


class TestMcp(unittest.TestCase):
    def test_handshake_and_tools(self):
        r = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}})
        self.assertEqual(r["result"]["serverInfo"]["name"], "movix")
        self.assertIsNone(mcp_server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        names = [t["name"] for t in mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]]
        self.assertEqual(names, config.MCP_TOOLS)
        self.assertIn("error", mcp_server.handle({"jsonrpc": "2.0", "id": 3, "method": "yok"}))

    def test_tool_without_blender_is_error_not_crash(self):
        os.environ["MOVIX_PORT"] = "1"
        os.environ["MOVIX_TOKEN"] = "x"
        res = mcp_server.call_tool("blender_scene_info", {})
        self.assertTrue(res["isError"])

    def test_stdio_roundtrip(self):
        p = subprocess.run([sys.executable, str(config.MCP_SCRIPT)], input=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n",
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(len(json.loads(p.stdout.splitlines()[0])["result"]["tools"]), 3)


class TestConfig(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(config.slug("Şirin Ağaç Çocuğu!"), "sirin-agac-cocugu")
        self.assertEqual(config.slug("../../etc"), "etc")
        self.assertEqual(config.slug("???"), "karakter")

    def test_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MOVIX_DOCS"] = tmp
            f = pipeline.unique_folder("Robot")
            (f / "frames").mkdir(parents=True)
            (f / "karakter.json").write_text(json.dumps({"title": "Robot", "character": "Knight"}), encoding="utf-8")
            (f / "frames" / "walk_right_01.png").write_bytes(b"x")
            self.assertEqual(pipeline.unique_folder("Robot").name, "robot-2")
            self.assertEqual([m["title"] for m in pipeline.list_characters()], ["Robot"])
            self.assertEqual(list(pipeline.load_frames(f)), ["walk_right"])
            del os.environ["MOVIX_DOCS"]


@unittest.skipUnless(config.find_blender(), "Blender kurulu değil")
class TestBlender(unittest.TestCase):
    """Başsız Blender'da karakter yükleme, parça karıştırma, boyama, süzgeç, animasyon, önizleme, kare ve sheet çizimi."""

    def test_selftest(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = subprocess.run([config.find_blender(), "-b", "--factory-startup", "--python", str(ROOT / "tests" / "blender_selftest.py"),
                                "--", "--no-serve", "--out", tmp], capture_output=True, text=True, timeout=300)
            line = next((ln for ln in p.stdout.splitlines() if ln.startswith("SELFTEST_JSON ")), None)
            self.assertIsNotNone(line, p.stdout[-1500:] + p.stderr[-1500:])
            r = json.loads(line[len("SELFTEST_JSON "):])
            self.assertTrue(r["run"]["ok"], r["run"])
            self.assertIn("Mage_Hat", r["run"]["scene"]["worn"])
            self.assertNotIn("Knight_Helmet", r["run"]["scene"]["worn"])
            self.assertTrue(r["run"]["scene"]["animated"])
            for k in ("blocked_os", "blocked_open", "blocked_wm", "blocked_dunder"):
                self.assertFalse(r[k]["ok"], k)
            for k in ("bad_part", "bad_color", "bad_character", "bad_anim", "bad_resize", "no_add"):
                self.assertFalse(r[k]["ok"], k)
            self.assertTrue(r["preview_exists"])
            self.assertEqual(r["frames"], {"idle": 6, "walk_right": 8, "walk_left": 8})
            self.assertTrue(r["sheet_exists"] and r["all_frames_exist"])
            self.assertTrue(r["save"]["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
