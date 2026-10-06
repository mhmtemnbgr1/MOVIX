"""Movix penceresi (Tkinter): solda karakter isteği + 3 öneri, sağda Blender'dan gelen animasyon kutucukları."""
from __future__ import annotations

import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import claude_runner, config, i18n, pipeline
from .i18n import t
from .blender_client import Blender, BlenderError  # noqa: F401

PAL = {"bg": "#0c0f16", "panel": "#141823", "panel2": "#1b2130", "panel3": "#232a3b", "border": "#262d3e", "text": "#e8ebf2", "dim": "#8a93a8",
       "accent": "#7c9cff", "accent_hi": "#9bb2ff", "on_accent": "#0b0f1a", "ok": "#4cc38a", "bad": "#ef5b5b", "warn": "#e8b64c"}
FONT = ("Segoe UI", 10)
FONT_B = ("Segoe UI", 10, "bold")
FONT_H = ("Segoe UI Semibold", 17)
FONT_T = ("Segoe UI Semibold", 12)
FONT_S = ("Segoe UI", 9)
FONT_SB = ("Segoe UI Semibold", 9)
FPS = {"walk_right": 8, "walk_left": 8, "idle": 6}


class ScrollFrame(tk.Frame):
    """Dikey kaydırılabilir alan: içerik sığmazsa kaydırma çubuğu çıkar, fare tekerleği çalışır."""

    def __init__(self, master: tk.Misc, bg: str) -> None:
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview, style="Dark.Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner.bind("<Configure>", lambda _e: self._sync())
        self.canvas.bind("<Configure>", self._on_canvas)
        self.winfo_toplevel().bind_all("<MouseWheel>", self._on_wheel, add="+")

    def _on_canvas(self, e: tk.Event) -> None:
        self.canvas.itemconfigure(self._win, width=e.width)
        self._sync()

    def _sync(self) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        need = self.inner.winfo_reqheight() > self.canvas.winfo_height() + 1
        if need and not self.bar.winfo_ismapped():
            self.bar.pack(side="right", fill="y", before=self.canvas)
        elif not need and self.bar.winfo_ismapped():
            self.bar.pack_forget()
            self.canvas.yview_moveto(0)

    def _inside(self, x: int, y: int) -> bool:
        w = self.winfo_containing(x, y)
        while w is not None:
            if w is self:
                return True
            w = w.master
        return False

    def _on_wheel(self, e: tk.Event) -> None:
        try:
            if self.bar.winfo_ismapped() and self._inside(e.x_root, e.y_root):
                self.canvas.yview_scroll(int(-e.delta / 120) * 3, "units")
        except tk.TclError:  # dil değişince eski panel yok edilmiş olabilir
            pass

    def scroll_to(self, widget: tk.Misc) -> None:
        """Verilen öğeyi görünür bölgenin üstüne getirir."""
        self.update_idletasks()
        total = max(1, self.inner.winfo_height())
        y = widget.winfo_rooty() - self.inner.winfo_rooty()
        self.canvas.yview_moveto(max(0.0, min(1.0, (y - 8) / total)))


class AnimBox(tk.Frame):
    """Bir animasyonun döngüde oynadığı kart."""

    def __init__(self, master: tk.Misc, title: str, size: int, shrink: bool = False) -> None:
        super().__init__(master, bg=PAL["panel"], highlightthickness=1, highlightbackground=PAL["border"])
        self.shrink = shrink  # dar ekranda 256 px kareler 3/4 boyuta indirilir
        size = size * 3 // 4 if shrink else size
        self.size = size
        head = tk.Frame(self, bg=PAL["panel"])
        head.pack(fill="x", padx=12, pady=(10, 6))
        tk.Frame(head, bg=PAL["accent"], width=3, height=14).pack(side="left", padx=(0, 8))
        tk.Label(head, text=title, bg=PAL["panel"], fg=PAL["text"], font=FONT_B).pack(side="left")
        self.canvas = tk.Canvas(self, width=size, height=size, bg=PAL["panel2"], highlightthickness=0)
        self.canvas.pack(padx=12)
        self.caption = tk.Label(self, text="", bg=PAL["panel"], fg=PAL["dim"], font=FONT_S)
        self.caption.pack(anchor="w", padx=12, pady=(6, 10))
        self._frames: list[tk.PhotoImage] = []
        self._fps = 8
        self._i = 0
        self._job: str | None = None
        self._item = self.canvas.create_image(size // 2, size // 2, image="")

    def set_frames(self, files: list[Path], fps: int) -> None:
        self.stop()
        self._frames = []
        for f in files:
            try:
                img = tk.PhotoImage(file=str(f))
            except tk.TclError:
                continue
            self._frames.append(img.zoom(3, 3).subsample(4, 4) if self.shrink else img)
        self._fps = max(1, fps)
        self._i = 0
        self.caption.config(text=t("frames_fps", len(self._frames), self._fps) if self._frames else "")
        if self._frames:
            self._tick()

    def clear(self) -> None:
        self.stop()
        self._frames = []
        self.canvas.itemconfig(self._item, image="")
        self.caption.config(text="")

    def stop(self) -> None:
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None

    def _tick(self) -> None:
        if not self._frames:
            return
        self.canvas.itemconfig(self._item, image=self._frames[self._i % len(self._frames)])
        self._i += 1
        self._job = self.after(int(1000 / self._fps), self._tick)


class App(tk.Tk):
    def __init__(self, boot: bool = True) -> None:
        super().__init__()
        self.title("Movix")
        self.configure(bg=PAL["bg"])
        assets = Path(__file__).parent / "assets"
        try:
            if sys.platform == "win32":
                import ctypes  # görev çubuğunda python.exe yerine kendi simgesi görünsün
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("movix.app")
                self.iconbitmap(default=str(assets / "icon.ico"))
            self._icon = tk.PhotoImage(file=str(assets / "icon.png")).subsample(4, 4)
            self.iconphoto(True, self._icon)
        except (tk.TclError, OSError):
            pass
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.compact = sw < 1500  # dar ekran: animasyon kutucukları küçülür
        self.left_w = 380 if self.compact else 420
        w, h = min(1320, int(sw * 0.94)), min(840, int(sh * 0.9))
        self.geometry("%dx%d+%d+%d" % (w, h, (sw - w) // 2, max(0, (sh - h) // 2 - 20)))
        self.minsize(min(1000, w), min(660, h))
        self.q: "queue.Queue" = queue.Queue()
        self.blender = Blender()
        self.cancel: claude_runner.Cancel | None = None
        self.busy = False
        self.ideas: list[dict] = []
        self.current: dict | None = None  # {title, concept, folder}
        self._placeholder = True
        self._pills = {"claude": ("", PAL["dim"]), "blender": ("", PAL["dim"])}
        self._log_entries: list = []
        self._style()
        self._build()
        self.update_idletasks()
        need = self.winfo_reqwidth() + 8  # içerik ne kadar genişlik istiyorsa pencere en az o kadar olsun
        w2 = min(max(w, need), sw - 10)
        self.geometry("%dx%d+%d+%d" % (w2, h, max(0, (sw - w2) // 2), max(0, (sh - h) // 2 - 20)))
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50, self._pump)
        if boot:
            self.after(200, self._boot)

    # --- Stil ve yerleşim -------------------------------------------------------------------------

    def _style(self) -> None:
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure("TCombobox", fieldbackground=PAL["panel2"], background=PAL["panel3"], foreground=PAL["text"], arrowcolor=PAL["text"],
                     bordercolor=PAL["border"], lightcolor=PAL["panel2"], darkcolor=PAL["panel2"], padding=4)
        st.map("TCombobox", fieldbackground=[("readonly", PAL["panel2"])], foreground=[("readonly", PAL["text"])])
        st.configure("Horizontal.TProgressbar", troughcolor=PAL["panel3"], background=PAL["accent"], bordercolor=PAL["panel3"],
                     lightcolor=PAL["accent"], darkcolor=PAL["accent"], thickness=6)
        st.configure("Dark.Vertical.TScrollbar", background=PAL["panel3"], troughcolor=PAL["panel"], bordercolor=PAL["panel"],
                     arrowcolor=PAL["dim"], lightcolor=PAL["panel3"], darkcolor=PAL["panel3"], gripcount=0, width=10)
        st.map("Dark.Vertical.TScrollbar", background=[("active", PAL["accent"])])
        self.option_add("*TCombobox*Listbox.background", PAL["panel2"])
        self.option_add("*TCombobox*Listbox.foreground", PAL["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", PAL["accent"])
        self.option_add("*TCombobox*Listbox.selectForeground", PAL["on_accent"])

    def _btn(self, parent: tk.Misc, text: str, cmd, accent: bool = False, small: bool = False) -> tk.Button:
        base = PAL["accent"] if accent else PAL["panel3"]
        hover = PAL["accent_hi"] if accent else PAL["border"]
        b = tk.Button(parent, text=text, command=cmd, font=FONT_B if accent else FONT, bd=0, relief="flat", padx=10 if small else 14,
                      pady=4 if small else 7, cursor="hand2", bg=base, fg=PAL["on_accent"] if accent else PAL["text"],
                      activebackground=hover, activeforeground=PAL["on_accent"] if accent else PAL["text"], disabledforeground=PAL["dim"],
                      highlightthickness=0)
        b.bind("<Enter>", lambda _e: b.config(bg=hover) if str(b["state"]) == "normal" else None)
        b.bind("<Leave>", lambda _e: b.config(bg=base))
        return b

    def _section(self, parent: tk.Misc, number: str, title: str, hint: str = "") -> None:
        row = tk.Frame(parent, bg=PAL["panel"])
        row.pack(fill="x", pady=(0, 6))
        tk.Label(row, text=number, bg=PAL["accent"], fg=PAL["on_accent"], font=FONT_SB, width=2).pack(side="left")
        tk.Label(row, text=title, bg=PAL["panel"], fg=PAL["text"], font=FONT_T).pack(side="left", padx=8)
        if hint:
            tk.Label(parent, text=hint, bg=PAL["panel"], fg=PAL["dim"], font=FONT_S, wraplength=self.left_w - 80, justify="left").pack(
                anchor="w", pady=(0, 8))

    def _build(self) -> None:
        top = tk.Frame(self, bg=PAL["panel"], highlightthickness=1, highlightbackground=PAL["border"])
        top.pack(fill="x", padx=14, pady=(14, 10))
        tk.Label(top, text="◆", bg=PAL["panel"], fg=PAL["accent"], font=("Segoe UI", 16)).pack(side="left", padx=(16, 6), pady=10)
        tk.Label(top, text="Movix", bg=PAL["panel"], fg=PAL["text"], font=FONT_H).pack(side="left")
        tk.Label(top, text=t("app_subtitle"), bg=PAL["panel"], fg=PAL["dim"], font=FONT).pack(side="left", padx=12)
        self.lang_btn = self._btn(top, t("lang_button"), self._toggle_lang, small=True)
        self.lang_btn.pack(side="right", padx=(6, 14))
        self.claude_pill = tk.Label(top, text="", bg=PAL["panel"], font=FONT_S)
        self.claude_pill.pack(side="right", padx=(6, 6))
        self.blender_pill = tk.Label(top, text="", bg=PAL["panel"], font=FONT_S)
        self.blender_pill.pack(side="right", padx=6)
        self.blender_btn = self._btn(top, t("pick_blender"), self._pick_blender, small=True)
        self._set_pill("claude", *self._pills["claude"])
        self._set_pill("blender", *self._pills["blender"])

        body = tk.Frame(self, bg=PAL["bg"])
        body.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        left = tk.Frame(body, bg=PAL["panel"], width=self.left_w, highlightthickness=1, highlightbackground=PAL["border"])
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        right = tk.Frame(body, bg=PAL["bg"])
        right.pack(side="left", fill="both", expand=True, padx=(14, 0))
        self._build_left(left)
        self._build_right(right)

    def _build_left(self, p: tk.Frame) -> None:
        # Alt çubuk (durum, ilerleme, iptal) kaydırmanın dışında kalır: iş sürerken her zaman görünür.
        footer = tk.Frame(p, bg=PAL["panel2"], highlightthickness=1, highlightbackground=PAL["border"])
        footer.pack(side="bottom", fill="x")
        fin = tk.Frame(footer, bg=PAL["panel2"])
        fin.pack(fill="x", padx=14, pady=10)
        self.status = tk.Label(fin, text=t("ready"), bg=PAL["panel2"], fg=PAL["dim"], font=FONT_S, wraplength=self.left_w - 60, justify="left", anchor="w")
        self.status.pack(fill="x")
        self.progress = ttk.Progressbar(fin, mode="indeterminate", style="Horizontal.TProgressbar")
        self.cancel_btn = self._btn(fin, t("cancel"), self._on_cancel, small=True)

        self.scroll = ScrollFrame(p, PAL["panel"])
        self.scroll.pack(side="top", fill="both", expand=True)
        inner = tk.Frame(self.scroll.inner, bg=PAL["panel"])
        inner.pack(fill="both", expand=True, padx=16, pady=14)

        self._section(inner, "1", t("sec1_title"), t("sec1_hint"))
        self.request = tk.Text(inner, height=4, wrap="word", bg=PAL["panel2"], fg=PAL["dim"], insertbackground=PAL["text"], bd=0, font=FONT,
                               padx=10, pady=8, highlightthickness=1, highlightbackground=PAL["border"], highlightcolor=PAL["accent"])
        self.request.pack(fill="x", pady=(0, 10))
        self.request.insert("1.0", t("placeholder"))
        self._placeholder = True
        self.request.bind("<FocusIn>", self._req_focus_in)
        self.request.bind("<FocusOut>", self._req_focus_out)
        self.request.bind("<Control-Return>", lambda _e: (self._suggest(), "break")[1])

        brow = tk.Frame(inner, bg=PAL["panel"])
        brow.pack(fill="x")
        self.suggest_btn = self._btn(brow, t("suggest"), self._suggest, accent=True)
        self.suggest_btn.pack(side="left", fill="x", expand=True)
        self.direct_btn = self._btn(brow, t("direct"), self._direct)
        self.direct_btn.pack(side="left", padx=(8, 0))

        self.cards = tk.Frame(inner, bg=PAL["panel"])
        self.cards.pack(fill="x", pady=(12, 0))

        tk.Frame(inner, bg=PAL["border"], height=1).pack(fill="x", pady=14)
        self._section(inner, "2", t("sec2_title"), t("sec2_hint"))
        rrow = tk.Frame(inner, bg=PAL["panel"])
        rrow.pack(fill="x", pady=(0, 4))
        self.refine = tk.Entry(rrow, bg=PAL["panel2"], fg=PAL["text"], insertbackground=PAL["text"], bd=0, font=FONT, highlightthickness=1,
                               highlightbackground=PAL["border"], highlightcolor=PAL["accent"])
        self.refine.pack(side="left", fill="x", expand=True, ipady=7)
        self.refine.bind("<Return>", lambda _e: self._refine())
        self.refine_btn = self._btn(rrow, t("apply"), self._refine)
        self.refine_btn.pack(side="left", padx=(8, 0))

    def _req_focus_in(self, _e=None) -> None:
        if self._placeholder:
            self.request.delete("1.0", "end")
            self.request.config(fg=PAL["text"])
            self._placeholder = False

    def _req_focus_out(self, _e=None) -> None:
        if not self.request.get("1.0", "end").strip():
            self.request.delete("1.0", "end")
            self.request.insert("1.0", t("placeholder"))
            self.request.config(fg=PAL["dim"])
            self._placeholder = True

    def _request_text(self) -> str:
        return "" if self._placeholder else self.request.get("1.0", "end").strip()

    def _build_right(self, p: tk.Frame) -> None:
        head = tk.Frame(p, bg=PAL["bg"])
        head.pack(fill="x")
        self.char_title = tk.Label(head, text=t("animations"), bg=PAL["bg"], fg=PAL["text"], font=FONT_H)
        self.char_title.pack(side="left")
        self.char_info = tk.Label(head, text="", bg=PAL["panel3"], fg=PAL["dim"], font=FONT_S, padx=10, pady=2)  # karakter etiketi: yalnızca karakter varken görünür
        boxes = tk.Frame(p, bg=PAL["bg"])
        boxes.pack(fill="x", pady=(12, 0))
        self.boxes: dict[str, AnimBox] = {}
        for i, (key, title) in enumerate(config.ANIMATIONS):
            b = AnimBox(boxes, t("anim_" + key), 256, shrink=self.compact)
            b.grid(row=0, column=i, padx=(0 if i == 0 else 12, 0), sticky="n")
            self.boxes[key] = b
        self.empty = tk.Label(p, text=t("empty"), bg=PAL["bg"], fg=PAL["dim"], font=FONT, wraplength=720, justify="left")
        self.empty.pack(anchor="w", pady=14)

        act = tk.Frame(p, bg=PAL["bg"])
        act.pack(fill="x", pady=(4, 0))
        self.folder_btn = self._btn(act, t("open_folder"), self._open_folder)
        self.folder_btn.pack(side="left")
        self.blend_btn = self._btn(act, t("open_blender"), self._open_in_blender)
        self.blend_btn.pack(side="left", padx=8)
        tk.Label(act, text=t("saved"), bg=PAL["bg"], fg=PAL["dim"], font=FONT_S).pack(side="left", padx=(18, 6))
        self.saved = ttk.Combobox(act, state="readonly", width=30, values=[])
        self.saved.pack(side="left")
        self.saved.bind("<<ComboboxSelected>>", self._load_saved)
        self._refresh_saved()

        lhead = tk.Frame(p, bg=PAL["bg"])
        lhead.pack(fill="x", pady=(16, 6))
        tk.Label(lhead, text=t("live"), bg=PAL["bg"], fg=PAL["text"], font=FONT_T).pack(side="left")
        tk.Label(lhead, text=t("live_sub"), bg=PAL["bg"], fg=PAL["dim"], font=FONT_S).pack(side="left", padx=8)
        self._btn(lhead, t("clear"), self._clear_log, small=True).pack(side="right")
        self.logbox = tk.Text(p, height=8, wrap="word", bg=PAL["panel"], fg=PAL["text"], bd=0, font=("Consolas", 9), padx=10, pady=8,
                              highlightthickness=1, highlightbackground=PAL["border"], state="disabled")
        self.logbox.pack(fill="both", expand=True)
        self.logbox.tag_config("ok", foreground=PAL["ok"])
        self.logbox.tag_config("bad", foreground=PAL["bad"])
        self.logbox.tag_config("dim", foreground=PAL["dim"])
        for stamp, text, tag in self._log_entries:  # dil değişince akış korunur
            self.logbox.config(state="normal")
            self.logbox.insert("end", stamp + text + "\n", tag or ())
            self.logbox.config(state="disabled")
        self.logbox.see("end")

    def _log(self, text: str, tag: str = "") -> None:
        stamp = time.strftime("%H:%M:%S  ")
        self._log_entries.append((stamp, text, tag))
        self.logbox.config(state="normal")
        self.logbox.insert("end", stamp + text + "\n", tag or ())
        self.logbox.see("end")
        self.logbox.config(state="disabled")

    def _clear_log(self) -> None:
        self._log_entries.clear()
        self.logbox.config(state="normal")
        self.logbox.delete("1.0", "end")
        self.logbox.config(state="disabled")

    def _toggle_lang(self) -> None:
        if self.busy:
            self.status.config(text=t("busy_wait"), fg=PAL["warn"])
            return
        i18n.set_lang("en" if i18n.get_lang() == "tr" else "tr")
        self._rebuild()

    def _rebuild(self) -> None:
        """Seçilen dille tüm arayüzü yeniden kurar; karakter, öneriler ve akış korunur."""
        request = self._request_text()
        refine = self.refine.get()
        for b in getattr(self, "boxes", {}).values():
            b.stop()
        for w in self.winfo_children():
            w.destroy()
        self._build()
        if request:
            self._req_focus_in()
            self.request.insert("1.0", request)
        self.refine.insert(0, refine)
        if self.ideas:
            self._on_ideas(self.ideas, None)
            self.status.config(text=t("ready"), fg=PAL["dim"])
        if self.current:
            self._show(self.current)
        if self._pills["blender"][0] in ("blender_missing", "blender_failed"):
            self.blender_btn.pack(side="right", padx=6)

    # --- İş parçacığı köprüsü -----------------------------------------------------------------------

    def post(self, fn, *args) -> None:
        self.q.put((fn, args))

    def _pump(self) -> None:
        try:
            while True:
                fn, args = self.q.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        self.after(50, self._pump)

    def _work(self, fn, on_done=None) -> None:
        """fn'yi arka planda çalıştırır; sonucu/hatayı arayüz iş parçacığında on_done(result, error) ile verir."""
        def run() -> None:
            try:
                res = fn()
                err = None
            except Exception as e:  # noqa: BLE001
                res, err = None, e
            if on_done is not None:
                self.post(on_done, res, err)
        threading.Thread(target=run, daemon=True).start()

    # --- Açılış ve durum ------------------------------------------------------------------------------

    def _set_pill(self, which: str, key: str, color: str) -> None:
        """Durum etiketini anahtarla saklar; dil değişince yeniden yazılabilir."""
        self._pills[which] = (key, color)
        label = self.claude_pill if which == "claude" else self.blender_pill
        label.config(text=t(key) if key else "", fg=color)

    def _boot(self) -> None:
        claude = config.find_claude()
        self._set_pill("claude", "claude_ready" if claude else "claude_missing", PAL["ok"] if claude else PAL["bad"])
        self._start_blender()

    def _start_blender(self) -> None:
        exe = config.find_blender()
        if not exe:
            self._set_pill("blender", "blender_missing", PAL["bad"])
            self.blender_btn.pack(side="right", padx=6)
            self.status.config(text=t("blender_not_installed"))
            return
        self.blender_btn.pack_forget()
        self._set_pill("blender", "blender_opening", PAL["warn"])
        self._work(lambda: self.blender.start(exe), self._on_blender_started)

    def _on_blender_started(self, _res, err) -> None:
        if err:
            self._set_pill("blender", "blender_failed", PAL["bad"])
            self.status.config(text=str(err))
            self.blender_btn.pack(side="right", padx=6)
        else:
            self._set_pill("blender", "blender_ok", PAL["ok"])

    def _pick_blender(self) -> None:
        path = filedialog.askopenfilename(title=t("dialog_blender"), filetypes=[("Blender", "blender.exe"), (t("all_files"), "*.*")])
        if path:
            s = config.load_settings()
            s["blender"] = path
            config.save_settings(s)
            self._start_blender()

    # --- Meşgul durumu ---------------------------------------------------------------------------------

    def _set_busy(self, on: bool, text: str = "") -> None:
        self.busy = on
        state = "disabled" if on else "normal"
        for b in (self.suggest_btn, self.direct_btn, self.refine_btn):
            b.config(state=state)
        for card_btn in self._card_buttons():
            card_btn.config(state=state)
        if on:
            self.progress.pack(fill="x", pady=(8, 6))
            self.progress.start(12)
            self.cancel_btn.pack(anchor="w")
        else:
            self.progress.stop()
            self.progress.pack_forget()
            self.cancel_btn.pack_forget()
        if text:
            self.status.config(text=text, fg=PAL["warn"] if on else PAL["dim"])
            self._log(text, "dim")

    def _card_buttons(self) -> list:
        return [w for card in self.cards.winfo_children() for w in card.winfo_children() if isinstance(w, tk.Button)]

    def _progress(self, text: str) -> None:
        def show() -> None:
            if not text.startswith("Claude: "):
                self.status.config(text=text, fg=PAL["warn"])
            self._log(text)
        self.post(show)

    def _error(self, err: Exception) -> None:
        msg = str(err)
        if msg == claude_runner.CANCELLED:
            self.status.config(text=t("cancelled"), fg=PAL["dim"])
            self._log(t("cancelled"), "dim")
        else:
            self.status.config(text=t("error") + msg, fg=PAL["bad"])
            self._log(t("error") + msg, "bad")
            messagebox.showerror("Movix", msg)

    def _on_cancel(self) -> None:
        if self.cancel is not None:
            self.status.config(text=t("cancelling"))
            self.cancel.set()

    def _need_ready(self) -> bool:
        if self.busy:
            self.status.config(text=t("busy_wait"), fg=PAL["warn"])
            self._log(t("busy_ignored"), "bad")
            return False
        if not config.find_claude():
            self.status.config(text=t("claude_not_found"), fg=PAL["bad"])
            self._log(t("claude_not_found_log"), "bad")
            return False
        return True

    # --- Öneri -----------------------------------------------------------------------------------------

    def _suggest(self) -> None:
        if not self._need_ready():
            return
        text = self._request_text()
        self.cancel = claude_runner.Cancel()
        self._set_busy(True, t("thinking"))
        c = self.cancel
        self._work(lambda: claude_runner.suggest(text, c), self._on_ideas)

    def _on_ideas(self, ideas, err) -> None:
        self._set_busy(False)
        if err:
            self._error(err)
            return
        self.ideas = ideas
        for w in self.cards.winfo_children():
            w.destroy()
        for n, idea in enumerate(ideas, 1):
            card = tk.Frame(self.cards, bg=PAL["panel2"], highlightthickness=1, highlightbackground=PAL["border"])
            card.pack(fill="x", pady=(0, 10))
            tk.Frame(card, bg=PAL["accent"], width=3).pack(side="left", fill="y")
            body = tk.Frame(card, bg=PAL["panel2"])
            body.pack(side="left", fill="x", expand=True, padx=12, pady=10)
            tk.Label(body, text="%d · %s" % (n, idea["title"]), bg=PAL["panel2"], fg=PAL["text"], font=FONT_B, anchor="w").pack(fill="x")
            tk.Label(body, text=idea["description"], bg=PAL["panel2"], fg=PAL["dim"], font=FONT_S, wraplength=self.left_w - 100, justify="left",
                     anchor="w").pack(fill="x", pady=(3, 8))
            self._btn(body, t("make"), lambda i=idea: self._start_build(i["title"], i["description"]), accent=True, small=True).pack(anchor="e")
        self.status.config(text=t("pick_one"), fg=PAL["dim"])
        self.after(50, lambda: self.scroll.scroll_to(self.cards))

    def _direct(self) -> None:
        text = self._request_text()
        if not text:
            self.status.config(text=t("describe_first"), fg=PAL["bad"])
            return
        self._start_build(" ".join(text.split()[:3]), text)

    # --- Üretim ----------------------------------------------------------------------------------------

    def _start_build(self, title: str, concept: str, refine: str | None = None) -> None:
        if not self._need_ready():
            return
        if not self.blender.running:
            self.status.config(text=t("blender_not_connected"), fg=PAL["bad"])
            self._log(t("blender_not_connected_log"), "bad")
            return
        self._log(t("log_change", refine) if refine else t("log_started", title), "ok")
        folder = Path(self.current["folder"]) if refine and self.current else None
        self.cancel = claude_runner.Cancel()
        c = self.cancel
        self._set_busy(True, t("working"))
        self._work(lambda: pipeline.make_character(self.blender, title, concept, self._progress, c, refine, folder),
                   lambda res, err: self._on_built(res, err, refine is not None))

    def _on_built(self, meta, err, was_refine: bool) -> None:
        self._set_busy(False)
        if err:
            self._error(err)
            return
        self.current = meta
        self._show(meta)
        self._refresh_saved()
        name = meta.get("character") or t("character")
        self.status.config(text=t("done_status", meta.get("title", ""), name), fg=PAL["ok"])
        self._log(t("log_done", meta.get("title", ""), name, meta.get("folder", "")), "ok")
        if meta.get("summary"):
            self._log(t("summary") + meta["summary"][:400])

    def _refine(self) -> None:
        text = self.refine.get().strip()
        if not text:
            return
        if not self.current:
            self.status.config(text=t("need_character"), fg=PAL["bad"])
            return
        self.refine.delete(0, "end")
        self._start_build(self.current["title"], self.current["concept"], refine=text)

    # --- Gösterim --------------------------------------------------------------------------------------

    def _show(self, meta: dict) -> None:
        folder = Path(meta["folder"])
        frames = pipeline.load_frames(folder)
        self.empty.pack_forget()
        self.char_title.config(text=meta.get("title", "Karakter"))
        self.char_info.config(text=meta.get("character") or t("character"))
        self.char_info.pack(side="left", padx=12)
        for key, _t in config.ANIMATIONS:
            if key in frames:
                self.boxes[key].set_frames(frames[key], FPS.get(key, 8))
            else:
                self.boxes[key].clear()

    def _refresh_saved(self) -> None:
        self.saved_items = pipeline.list_characters()
        self.saved.config(values=["%s  (%s)" % (m.get("title", "?"), m.get("character") or t("character")) for m in self.saved_items])

    def _load_saved(self, _e=None) -> None:
        i = self.saved.current()
        if 0 <= i < len(self.saved_items):
            self.current = self.saved_items[i]
            self._show(self.current)

    def _open_folder(self) -> None:
        folder = (self.current or {}).get("folder") or str(config.output_root())
        if sys.platform == "win32":
            Path(folder).mkdir(parents=True, exist_ok=True)
            os.startfile(folder)  # noqa: S606

    def _open_in_blender(self) -> None:
        exe = config.find_blender()
        if not (self.current and exe):
            return
        blend = Path(self.current["folder"]) / "karakter.blend"
        if blend.exists():
            self.blender.open_file(exe, blend)

    def _on_close(self) -> None:
        if self.cancel is not None:
            self.cancel.set()
        for b in self.boxes.values():
            b.stop()
        self.blender.stop()
        self.destroy()


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
