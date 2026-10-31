"""GPO Fishing Macro: the app window (CustomTkinter) for the macOS fishing macro.

The window only edits settings and shows state. The fishing itself runs in
fishing.Fisher on a worker thread; its callbacks reach Tk through a queue
that the Tk loop drains every 15 ms.
"""
from __future__ import annotations

import base64
import platform
import queue
import subprocess
import threading
import time
import tkinter as tk
import traceback
from tkinter import messagebox

import customtkinter as ctk
import cv2
import mss
import numpy as np

import config
import platform_keys
from detect import Detector, Reading
from fishing import Catch, Fisher, Hooks, bar_box, check_ready, grab, read_bait_count, read_new_item, row_spot
from point_selector import ClickCapture, FracPoint
from roblox_geo import roblox_client_rect
from screen_text import row_bait
from win_focus import focus_roblox

RUN_LOG = config.CONFIG_PATH.parent / "run-log.txt"
RUN_LOG_MAX_BYTES = 512 * 1024
LOG_LINES = 300
GAUGE_W, GAUGE_H = 230, 420
CAPTION_H = 40
# The gauge is for people, not the detector; 8 fps keeps Tk light.
GAUGE_MS = 125

PAPER = "#FFFFFF"
FIELD = "#F2F2F4"
INK = "#1D1D1F"
INK_HOVER = "#3A3A3D"
MUTED = "#6E6E73"
RULE = "#E5E5EA"
GREEN = "#248A3D"
RED = "#D70015"
RED_HOVER = "#B00012"


def run_log(msg: str) -> None:
    if RUN_LOG.exists() and RUN_LOG.stat().st_size > RUN_LOG_MAX_BYTES:
        RUN_LOG.write_text("", encoding="utf-8")
    with open(RUN_LOG, "a", encoding="utf-8") as f:
        f.write("%s  %s\n" % (time.strftime("%H:%M:%S"), msg))


def annotate(image: np.ndarray, reading: Reading | None, height: int) -> np.ndarray:
    """Scale the scan frame to `height` and draw the gap (cyan) and fish (magenta)."""
    s = height / image.shape[0]
    vis = cv2.resize(image, (max(1, int(image.shape[1] * s)), height), interpolation=cv2.INTER_AREA)
    if reading is not None:
        x0 = int((reading.bar_x0 - 4) * s)
        x1 = int((reading.bar_x1 + 4) * s)
        cv2.rectangle(vis, (x0, int(reading.gap_top * s)), (x1, int(reading.gap_bot * s)), (255, 255, 80), 2)
        fy = int(reading.fish_y * s)
        cv2.line(vis, (x0 - 8, fy), (x1 + 8, fy), (255, 80, 255), 2)
    return vis


class App(ctk.CTk):
    def __init__(self, cfg: dict) -> None:
        super().__init__(fg_color=PAPER)
        self.cfg = cfg
        self.title("GPO Fishing Macro")
        self.resizable(False, False)

        self._posted: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self._frame: tuple[np.ndarray, Reading | None] | None = None
        self._shown_frame = None
        self._gauge_img: tk.PhotoImage | None = None
        self._picker: tk.Toplevel | None = None
        self._started_at = 0.0
        self._last_item: str | None = None
        self._rarities: dict[str, int] = {}
        self._stats = dict.fromkeys(("cast", "bite", "caught", "lost", "unclear", "timeout"), 0)
        self._lockable: list = []
        self._bait_rows: list[dict] = []
        self._log_lines: list[str] = []
        self._log_win: ctk.CTkToplevel | None = None
        self._tune_win: ctk.CTkToplevel | None = None
        self._hidden: list[tk.Misc] = []

        self._f_title = ctk.CTkFont(size=20, weight="bold")
        self._f_head = ctk.CTkFont(size=15, weight="bold")
        self._f_num = ctk.CTkFont(size=24, weight="bold")
        self._f_body = ctk.CTkFont(size=13)
        self._f_bold = ctk.CTkFont(size=13, weight="bold")
        self._f_small = ctk.CTkFont(size=11)

        self._build()
        self._apply_topmost()

        platform_keys.add_hotkey("F1", lambda: self._post(self._toggle_run))
        platform_keys.add_hotkey("F3", lambda: self._post(self._on_close))
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(15, self._pump)
        self.after(400, self._check_permissions)
        self._set_status("Equip your rod in GPO, then start fishing.")

    # ---------- widgets ----------

    def _label(self, parent, text="", font=None, color=INK, **kw) -> ctk.CTkLabel:
        return ctk.CTkLabel(parent, text=text, font=font or self._f_body, text_color=color, anchor="w",
                            justify="left", **kw)

    def _button(self, parent, text, command, width=0, **kw) -> ctk.CTkButton:
        return ctk.CTkButton(parent, text=text, command=command, corner_radius=5, height=30, font=self._f_body,
                             width=width, fg_color=FIELD, hover_color=RULE, text_color=INK, **kw)

    def _entry(self, parent, var, width, **kw) -> ctk.CTkEntry:
        return ctk.CTkEntry(parent, textvariable=var, width=width, height=30, corner_radius=4, border_width=1,
                            border_color=RULE, fg_color=FIELD, text_color=INK, font=self._f_body, **kw)

    def _check(self, parent, text, var, command) -> ctk.CTkCheckBox:
        return ctk.CTkCheckBox(parent, text=text, variable=var, command=command, font=self._f_body,
                               text_color=INK, fg_color=INK, hover_color=INK_HOVER, border_color=MUTED,
                               border_width=1, corner_radius=3, checkbox_width=18, checkbox_height=18)

    def _section(self, parent, title: str) -> ctk.CTkFrame:
        self._label(parent, title, self._f_head).pack(fill="x", pady=(14, 4))
        f = ctk.CTkFrame(parent, fg_color=PAPER)
        f.pack(fill="x")
        return f

    # ---------- layout ----------

    def _build(self) -> None:
        head = ctk.CTkFrame(self, fg_color=PAPER)
        head.pack(fill="x", padx=22, pady=(16, 0))
        self._label(head, "GPO Fishing Macro", self._f_title).pack(side="left")
        self._start = ctk.CTkButton(head, text="Start fishing   F1", command=self._toggle_run, corner_radius=5,
                                    height=38, width=190, font=ctk.CTkFont(size=13, weight="bold"),
                                    fg_color=INK, hover_color=INK_HOVER, text_color=PAPER)
        self._start.pack(side="right")
        self._status = self._label(self, "", wraplength=600)
        self._status.pack(fill="x", padx=22, pady=(2, 10))
        tk.Frame(self, height=1, bg=RULE).pack(fill="x", padx=22)

        main = ctk.CTkFrame(self, fg_color=PAPER)
        main.pack(fill="both", expand=True, padx=22, pady=(14, 18))
        left = ctk.CTkFrame(main, fg_color=PAPER, width=GAUGE_W)
        left.pack(side="left", fill="y")
        right = ctk.CTkFrame(main, fg_color=PAPER)
        right.pack(side="left", fill="both", expand=True, padx=(22, 0))

        self._build_gauge(left)
        self._build_readout(right)
        self._build_baits(self._section(right, "Bait"))
        self._build_setup(self._section(right, "Setup"))

    def _build_gauge(self, f) -> None:
        self._gauge = tk.Canvas(f, width=GAUGE_W, height=GAUGE_H, bg=PAPER, highlightthickness=0, bd=0)
        self._gauge.pack()
        self._draw_idle_gauge()

    def _draw_idle_gauge(self) -> None:
        c = self._gauge
        c.delete("all")
        h = GAUGE_H - CAPTION_H
        c.create_rectangle(1, 1, GAUGE_W - 1, h, fill=FIELD, outline="")
        c.create_text(GAUGE_W // 2, h // 2, text="Scan preview", fill=MUTED, font=self._f_body)
        self._caption("Shows the bars while fishing, or after Test detection.", MUTED, h)

    def _caption(self, text: str, color: str, y: int) -> None:
        self._gauge.create_text(0, y + 8, text=text, fill=color, font=self._f_small, anchor="nw",
                                width=GAUGE_W)

    def _build_readout(self, f) -> None:
        row = ctk.CTkFrame(f, fg_color=PAPER)
        row.pack(fill="x")
        self._nums = {}
        for key, word in (("caught", "caught"), ("lost", "lost"), ("cast", "casts"), ("rate", "an hour")):
            n = self._label(row, "0" if key != "rate" else "–", self._f_num)
            n.pack(side="left")
            self._label(row, word, self._f_body, MUTED).pack(side="left", padx=(4, 16), pady=(10, 0))
            self._nums[key] = n
        self._clock = self._label(f, "Not fishing yet.", self._f_small, MUTED)
        self._clock.pack(fill="x")

    def _build_baits(self, f) -> None:
        self._bait_box = ctk.CTkFrame(f, fg_color=PAPER)
        self._bait_box.pack(fill="x")
        self._label(f, "Ticked baits are used top to bottom, keeping the last one of each. "
                       "When all are down to 1, the app casts and reels in once a minute so you "
                       "don't get kicked for AFK. The app reads the game's bait panel to find each "
                       "bait, and skips a ticked bait you have none of.",
                    self._f_small, MUTED, wraplength=420).pack(fill="x", pady=(2, 0))
        self._render_baits()

    def _render_baits(self) -> None:
        for row in self._bait_rows:
            row["frame"].destroy()
        self._bait_rows.clear()
        last = len(self.cfg["baits"]) - 1
        for i, bait in enumerate(self.cfg["baits"]):
            fr = ctk.CTkFrame(self._bait_box, fg_color=PAPER)
            fr.pack(fill="x", pady=3)
            top = ctk.CTkFrame(fr, fg_color=PAPER)
            top.pack(fill="x")
            use = tk.BooleanVar(value=bait["use"])
            cb = self._check(top, bait["name"], use, lambda i=i, v=use: self._set_bait_use(i, v.get()))
            cb.pack(side="left")
            down = self._button(top, "↓", lambda i=i: self._move_bait(i, 1), width=30)
            down.pack(side="right")
            up = self._button(top, "↑", lambda i=i: self._move_bait(i, -1), width=30)
            up.pack(side="right", padx=(0, 2))
            count = self._label(top, "", self._f_small, MUTED)
            count.pack(side="right", padx=(0, 10))
            self._label(fr, config.BAIT_TYPES[bait["name"]], self._f_small, MUTED).pack(fill="x", padx=(28, 0))
            # The row keeps `use` alive; Tk drops a variable nothing references.
            self._bait_rows.append({"frame": fr, "count": count, "use": cb, "use_var": use,
                                    "up": (up, i > 0), "down": (down, i < last)})
        self._refresh_baits()

    def _refresh_baits(self) -> None:
        running = self._running()
        for i, (row, bait) in enumerate(zip(self._bait_rows, self.cfg["baits"])):
            n = bait["count"]
            text = "count unknown" if n is None else f"{n} left"
            in_use = running and i == self.cfg["bait_index"]
            row["count"].configure(text=text + (", in use" if in_use else ""), text_color=GREEN if in_use else MUTED)
            row["use"].configure(state="disabled" if running else "normal")
            for button, movable in (row["up"], row["down"]):
                button.configure(state="normal" if movable and not running else "disabled")

    def _set_bait_use(self, i: int, use: bool) -> None:
        self.cfg["baits"][i]["use"] = bool(use)
        self._save()

    def _move_bait(self, i: int, step: int) -> None:
        baits = self.cfg["baits"]
        baits[i], baits[i + step] = baits[i + step], baits[i]
        self.cfg["bait_index"] = 0
        self._save()
        self._render_baits()

    def _build_setup(self, f) -> None:
        def line(label: str) -> tuple[ctk.CTkFrame, ctk.CTkLabel]:
            fr = ctk.CTkFrame(f, fg_color=PAPER)
            fr.pack(fill="x", pady=3)
            self._label(fr, label, self._f_bold, width=96).pack(side="left", anchor="n", pady=(4, 0))
            value = self._label(fr, "", self._f_small, MUTED, wraplength=190)
            value.pack(side="left", fill="x", expand=True)
            return fr, value

        fr, self._cast_lbl = line("Cast spot")
        b = self._button(fr, "Pick spot", self._set_cast_point, width=104)
        b.pack(side="right")
        self._lockable.append(b)

        fr, hint = line("Rod key")
        hint.configure(text="Optional. Re-equips the rod after 3 casts with no bite.")
        self._rod_var = tk.StringVar(value=self.cfg["rod_key"])
        e = self._entry(fr, self._rod_var, 104, justify="center")
        e.pack(side="right")
        e.bind("<FocusOut>", lambda _e: self._commit_rod_key())
        e.bind("<Return>", lambda _e: self._commit_rod_key())
        self._lockable.append(e)

        self._top_var = tk.BooleanVar(value=self.cfg["always_on_top"])
        self._buy_var = tk.BooleanVar(value=self.cfg["auto_buy_common"])
        buy = self._check(f, "Buy Common Fish Bait when all bait is down to 1 (stand by the seller)",
                          self._buy_var, self._on_buy)
        buy.pack(anchor="w", pady=(8, 3))
        self._lockable.append(buy)
        self._buso_var = tk.BooleanVar(value=self.cfg["use_buso"])
        buso = self._check(f, "Use Buso Haki: press J after a catch, once a minute", self._buso_var,
                           self._on_buso)
        buso.pack(anchor="w", pady=3)
        self._lockable.append(buso)
        self._check(f, "Keep this window on top", self._top_var, self._on_options).pack(anchor="w", pady=3)

        row = ctk.CTkFrame(f, fg_color=PAPER)
        row.pack(fill="x", pady=(10, 0))
        b = self._button(row, "Test detection", self._test_detection)
        b.pack(side="left")
        self._lockable.append(b)
        b = self._button(row, "Test buy", self._test_buy)
        b.pack(side="left", padx=(8, 0))
        self._lockable.append(b)
        self._button(row, "Tuning…", self._open_tuning).pack(side="left", padx=(8, 0))
        self._button(row, "Log…", self._open_log).pack(side="left", padx=(8, 0))
        self._refresh_setup()

    def _refresh_setup(self) -> None:
        p = self.cfg["cast_point"]
        self._cast_lbl.configure(text="Clicks at %.0f%% across, %.0f%% down." % (p["x"] * 100, p["y"] * 100)
                                 if p else "Not picked yet.")

    # ---------- helpers ----------

    @staticmethod
    def _fmt(v: float) -> str:
        return ("%.4f" % v).rstrip("0").rstrip(".")

    def _post(self, fn) -> None:
        self._posted.put(fn)

    def _pump(self) -> None:
        while True:
            try:
                fn = self._posted.get_nowait()
            except queue.Empty:
                break
            fn()
        self.after(15, self._pump)

    def _running(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def _save(self) -> None:
        config.save(self.cfg)

    def _set_status(self, text: str, error: bool = False) -> None:
        self._status.configure(text=text, text_color=RED if error else MUTED)
        self._append_log(text)

    def _append_log(self, text: str) -> None:
        run_log(text)
        line = "%s  %s" % (time.strftime("%H:%M:%S"), text)
        self._log_lines = (self._log_lines + [line])[-LOG_LINES:]
        if self._log_win is not None and self._log_win.winfo_exists():
            box = self._log_win.box
            box.configure(state="normal")
            box.insert("end", line + "\n")
            box.see("end")
            box.configure(state="disabled")

    def _show_frame(self, image: np.ndarray, reading: Reading | None) -> None:
        vis = annotate(image, reading, GAUGE_H - CAPTION_H - 4)
        if vis.shape[1] > GAUGE_W - 4:
            vis = annotate(image, reading, int((GAUGE_H - CAPTION_H - 4) * (GAUGE_W - 4) / vis.shape[1]))
        ok, png = cv2.imencode(".png", vis)
        if not ok:
            raise RuntimeError("could not encode the gauge image")
        self._gauge_img = tk.PhotoImage(data=base64.b64encode(png.tobytes()))
        h, w = vis.shape[:2]
        x0 = (GAUGE_W - w) // 2
        c = self._gauge
        c.delete("all")
        c.create_image(x0, 3, image=self._gauge_img, anchor="nw")
        c.create_rectangle(x0 - 1, 2, x0 + w, h + 3, outline=RULE, width=1)
        if reading is None:
            self._caption("Waiting for the bars.", MUTED, h + 3)
        elif reading.progress is None:
            self._caption("Bars found. Catch meter not seen.", MUTED, h + 3)
        else:
            self._caption("Catch meter %.0f%%" % (reading.progress * 100), GREEN, h + 3)

    # ---------- settings ----------

    def _commit_rod_key(self) -> None:
        key = self._rod_var.get().strip().lower()
        if key and key not in platform_keys.KEY_NAMES:
            self._set_status(f"Rod key {key!r} can't be pressed. Use one key, 0-9 or a-z, or leave it empty.",
                             error=True)
            self._rod_var.set(self.cfg["rod_key"])
            return
        self._rod_var.set(key)
        self.cfg["rod_key"] = key
        self._save()

    def _on_options(self) -> None:
        self.cfg["always_on_top"] = bool(self._top_var.get())
        self._save()
        self._apply_topmost()

    def _on_buy(self) -> None:
        self.cfg["auto_buy_common"] = bool(self._buy_var.get())
        self._save()

    def _on_buso(self) -> None:
        self.cfg["use_buso"] = bool(self._buso_var.get())
        self._save()

    def _apply_topmost(self) -> None:
        self.attributes("-topmost", bool(self.cfg["always_on_top"]))

    # ---------- side windows ----------

    def _side_window(self, title: str) -> ctk.CTkToplevel:
        win = ctk.CTkToplevel(self, fg_color=PAPER)
        win.title(title)
        win.transient(self)
        return win

    def _open_log(self) -> None:
        if self._log_win is not None and self._log_win.winfo_exists():
            self._log_win.lift()
            return
        win = self._side_window("GPO Fishing Macro log")
        win.geometry("560x360")
        box = ctk.CTkTextbox(win, fg_color=FIELD, text_color=INK, font=self._f_small, corner_radius=6, wrap="word")
        box.pack(fill="both", expand=True, padx=14, pady=14)
        box.insert("end", "\n".join(self._log_lines) + "\n")
        box.see("end")
        box.configure(state="disabled")
        win.box = box
        self._log_win = win

    def _open_tuning(self) -> None:
        if self._tune_win is not None and self._tune_win.winfo_exists():
            self._tune_win.lift()
            return
        win = self._side_window("Tuning")
        self._label(win, "Tuning", self._f_head).pack(fill="x", padx=18, pady=(14, 0))
        self._label(win, "Change these only when the gap overshoots or lags behind the fish.",
                    self._f_small, MUTED).pack(fill="x", padx=18)
        grid = ctk.CTkFrame(win, fg_color=PAPER)
        grid.pack(fill="x", padx=18, pady=10)
        grid.grid_columnconfigure(0, weight=1)
        self._adv_vars: dict[str, tk.StringVar] = {}
        for r, (key, label) in enumerate(config.ADVANCED_LABELS.items()):
            self._label(grid, label).grid(row=r, column=0, sticky="w", pady=2, padx=(0, 16))
            var = tk.StringVar(value=self._fmt(self.cfg["advanced"][key]))
            e = self._entry(grid, var, 90, justify="right")
            e.grid(row=r, column=1, pady=2)
            e.bind("<FocusOut>", lambda _e, k=key: self._commit_advanced(k))
            e.bind("<Return>", lambda _e, k=key: self._commit_advanced(k))
            if self._running():
                e.configure(state="disabled")
            self._adv_vars[key] = var
        self._button(win, "Reset to defaults", self._reset_advanced).pack(anchor="w", padx=18, pady=(0, 16))
        self._tune_win = win

    def _commit_advanced(self, key: str) -> None:
        raw = self._adv_vars[key].get().strip()
        try:
            v = float(raw)
        except ValueError:
            v = None
        if v is None or (v <= 0 and key != "aim_offset"):
            self._set_status(f"{config.ADVANCED_LABELS[key]}: {raw!r} is not valid. Type a number above 0.",
                             error=True)
            self._adv_vars[key].set(self._fmt(self.cfg["advanced"][key]))
            return
        self.cfg["advanced"][key] = v
        self._save()

    def _reset_advanced(self) -> None:
        if self._running():
            self._set_status("Stop fishing before you reset tuning.", error=True)
            return
        self.cfg["advanced"] = dict(config.ADVANCED_DEFAULTS)
        for k, var in self._adv_vars.items():
            var.set(self._fmt(self.cfg["advanced"][k]))
        self._save()
        self._set_status("Tuning reset to defaults.")

    # ---------- pickers ----------

    def _picker_blocked(self) -> bool:
        if self._running():
            self._set_status("Stop fishing first.", error=True)
            return True
        return self._picker is not None and self._picker.winfo_exists()

    def _capture_point(self, prompt: str, on_point) -> None:
        if self._picker_blocked():
            return
        focus_roblox()

        def saved(pt: FracPoint, source: str) -> None:
            self._picker = None
            on_point({"x": pt.x, "y": pt.y})
            self._save()
            self._set_status("Spot saved." if source == "roblox"
                             else "Spot saved relative to the screen. Open GPO and pick it again.",
                             error=source != "roblox")

        def cancelled() -> None:
            self._picker = None
            self._set_status("Spot not changed.")

        self._picker = ClickCapture(self, prompt=prompt, on_saved=saved, on_cancelled=cancelled)

    def _set_cast_point(self) -> None:
        def store(p: dict) -> None:
            self.cfg["cast_point"] = p
            self._refresh_setup()
        self._capture_point("Click the open water where the rod should cast", store)

    # ---------- detection test ----------

    def _test_detection(self) -> None:
        if self._picker_blocked():
            return
        window = roblox_client_rect()
        if window is None:
            self._set_status("GPO isn't open. Open it, fish once by hand, and test while the bars show.",
                             error=True)
            return
        d = Detector()
        with (getattr(mss, "MSS", None) or mss.mss)() as sct:
            image = grab(window, sct)
            reading = d.find(image)
            if reading is not None:
                # Show and re-read only the box around the bars, as a run does.
                image = grab(bar_box(reading, window, window), sct)
                reading = Detector().find(image)
        self._show_frame(image, reading)
        self._test_bait_counts()
        catch, why = read_new_item()
        self._append_log(f"New Item banner: {catch.name} ({catch.rarity})." if catch
                         else f"New Item banner not seen ({why}).")
        if reading is None:
            self._set_status(f"Bars not found: {d.last}. Run Test detection while the bars are on screen.",
                             error=True)
            return
        self._set_status("Bars found. The cyan box should sit on the gap and the magenta line on the fish.")

    def _test_bait_counts(self) -> None:
        """Read the bait panel row by row, as a run does, and show what is in it."""
        listed = set()
        for k in range(len(config.BAIT_TYPES)):
            count, row = read_bait_count(row_spot(k))
            name = row_bait(row, list(config.BAIT_TYPES)) if row else None
            if name is None:
                self._append_log(f"Bait panel row {k + 1}: {'empty' if not row else repr(row)}.")
                break
            listed.add(name)
            bait = next(b for b in self.cfg["baits"] if b["name"] == name)
            if count is None:
                self._append_log(f"Bait panel row {k + 1}: {name}, count not read ({row!r}).")
            else:
                bait["count"] = count
                self._append_log(f"Bait panel row {k + 1}: {name}, {count} left.")
        for bait in self.cfg["baits"]:
            if bait["use"] and bait["name"] not in listed:
                self._append_log(f"{bait['name']} is not in the panel; a run skips it.")
        self._save()
        self._refresh_baits()

    # ---------- run ----------

    def _toggle_run(self) -> None:
        if self._running():
            self._stop.set()
            self._set_status("Stopping...")
            return
        if self._picker is not None and self._picker.winfo_exists():
            self._set_status("Finish the open picker first.", error=True)
            return
        self.focus_set()
        reason = check_ready(self.cfg)
        if reason:
            self._set_status(reason, error=True)
            return
        self._stats = dict.fromkeys(self._stats, 0)
        self._last_item = None
        self._rarities = {}
        self._started_at = time.monotonic()
        self._refresh_numbers()
        self._start_worker(lambda fisher: fisher.run(), "Fishing started.")
        self.after(GAUGE_MS, self._tick_gauge)
        self.after(1000, self._tick_clock)

    def _test_buy(self) -> None:
        """Run the Common Fish Bait purchase once, as auto-buy would."""
        if self._picker_blocked():
            return
        self._start_worker(lambda fisher: fisher.buy_once(),
                           "Test buy started. Stand next to the Common Fish Bait seller. F1 stops it.")

    def _start_worker(self, job, message: str) -> None:
        """Run job(fisher) on the worker thread with the run controls locked."""
        self._stop = threading.Event()
        hooks = Hooks(
            status=lambda m: self._post(lambda: self._set_status(m)),
            event=lambda k, catch: self._post(lambda: self._on_event(k, catch)),
            frame=self._on_frame,
            bait_changed=lambda: self._post(self._on_bait_changed),
        )
        fisher = Fisher(self.cfg, hooks, should_abort=self._stop.is_set)
        self._worker = threading.Thread(target=self._work, args=(fisher, job), daemon=True)
        self._worker.start()
        self._hide_windows_over_game()
        self._start.configure(text="Stop   F1", fg_color=RED, hover_color=RED_HOVER)
        for w in self._lockable:
            w.configure(state="disabled")
        self._refresh_baits()
        self._set_status(message)

    def _work(self, fisher: Fisher, job) -> None:
        try:
            reason = job(fisher)
        except Exception as exc:
            run_log(traceback.format_exc())
            reason = f"Stopped by an error: {exc}. Details are in run-log.txt."
        self._post(lambda: self._on_run_ended(reason))
        if fisher.disconnected:
            # The user asked for the macro to quit with Roblox on a disconnect.
            self._post(self._on_close)

    def _hide_windows_over_game(self) -> None:
        """Minimize app windows that overlap Roblox, so clicks reach the game.

        On 2026-10-24 the log window sat over the cast spot and swallowed every
        cast click. F1 still works while the windows are minimized.
        """
        game = roblox_client_rect()
        if game is None:
            return
        self._hidden = []
        for win in (self._log_win, self._tune_win, self):
            if win is None or not win.winfo_exists() or win.state() != "normal":
                continue
            x, y, w, h = win.winfo_rootx(), win.winfo_rooty(), win.winfo_width(), win.winfo_height()
            if x < game.x + game.w and game.x < x + w and y < game.y + game.h and game.y < y + h:
                self._hidden.append(win)
        for win in self._hidden:
            win.iconify()
        if self._hidden:
            self._append_log("Minimized the app because it covered the game. Press F1 to stop.")

    def _on_run_ended(self, reason: str) -> None:
        self._worker = None
        for win in reversed(self._hidden):
            if win.winfo_exists():
                win.deiconify()
        self._hidden = []
        self._start.configure(text="Start fishing   F1", fg_color=INK, hover_color=INK_HOVER)
        for w in self._lockable:
            w.configure(state="normal")
        self._refresh_baits()
        self._save()
        self._set_status(reason, error=not reason.startswith(("Stopped.", "Test buy done")))
        if self._rarities:
            self._append_log("Session catches: " + ", ".join(
                f"{n} {r}" for r, n in sorted(self._rarities.items(), key=lambda kv: -kv[1])) + ".")

    def _on_frame(self, image: np.ndarray, reading: Reading | None) -> None:
        self._frame = (image, reading)

    def _tick_gauge(self) -> None:
        if not self._running():
            return
        frame = self._frame
        if frame is not None and frame is not self._shown_frame:
            self._shown_frame = frame
            self._show_frame(*frame)
        self.after(GAUGE_MS, self._tick_gauge)

    def _tick_clock(self) -> None:
        if not self._running():
            return
        el = time.monotonic() - self._started_at
        last = f" Last catch: {self._last_item}." if self._last_item else ""
        self._clock.configure(text="Fishing for %s.%s" % (time.strftime("%H:%M:%S", time.gmtime(el)), last))
        if el >= 60:
            self._nums["rate"].configure(text="%.0f" % (self._stats["caught"] * 3600 / el))
        self.after(1000, self._tick_clock)

    def _refresh_numbers(self) -> None:
        for key in ("cast", "caught", "lost"):
            self._nums[key].configure(text=str(self._stats[key]))
        self._nums["rate"].configure(text="–")

    def _on_event(self, kind: str, catch: Catch | None) -> None:
        self._stats[kind] += 1
        for key in ("cast", "caught", "lost"):
            self._nums[key].configure(text=str(self._stats[key]))
        if catch is not None:
            self._last_item = f"{catch.name} ({catch.rarity})"
            self._rarities[catch.rarity] = self._rarities.get(catch.rarity, 0) + 1
        notes = {"caught": f"Caught {self._last_item}." if catch else "Caught a fish.",
                 "lost": "The fish got away.",
                 "unclear": "Minigame ended. The catch meter was not seen, so the result is unknown.",
                 "timeout": "Minigame ran past the time limit. Casting again."}
        if kind in notes:
            self._append_log(notes[kind])

    def _on_bait_changed(self) -> None:
        self._refresh_baits()
        self._save()

    # ---------- startup and shutdown ----------

    def _check_permissions(self) -> None:
        import Quartz
        from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt

        major = platform.mac_ver()[0].split(".")[0]
        where = ("System Preferences > Security & Privacy > Privacy" if major in ("11", "12")
                 else "System Settings > Privacy & Security")
        missing = []
        if not Quartz.CGPreflightScreenCaptureAccess():
            Quartz.CGRequestScreenCaptureAccess()
            missing.append(("Screen Recording", "Privacy_ScreenCapture"))
        if not Quartz.CGPreflightListenEventAccess():
            Quartz.CGRequestListenEventAccess()
            missing.append(("Input Monitoring", "Privacy_ListenEvent"))
        if not AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True}):
            missing.append(("Accessibility", "Privacy_Accessibility"))
        if not missing:
            return
        names = [n for n, _ in missing]
        self._set_status("Allow %s for Terminal under %s, then open the app again." % (" and ".join(names), where),
                         error=True)
        if messagebox.askyesno(
            "Permissions needed",
            "The macro needs these permissions, granted to Terminal:\n\n    %s\n\n"
            "They are under %s. Turn Terminal on in each list, then quit Terminal "
            "(Cmd-Q) and open the app again.\n\nOpen %s settings now?"
            % ("\n    ".join(names), where, names[0]),
            parent=self,
        ):
            subprocess.Popen(["open", "x-apple.systempreferences:com.apple.preference.security?" + missing[0][1]])

    def _on_close(self) -> None:
        self._stop.set()
        if self._worker is not None:
            # The worker checks the stop flag every frame and in every sleep.
            self._worker.join(timeout=2.0)
        platform_keys.unhook_all()
        self._save()
        self.destroy()


def main() -> None:
    try:
        cfg = config.load()
    except config.ConfigError as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("GPO Fishing Macro: settings problem", str(exc))
        root.destroy()
        raise SystemExit(1)
    ctk.set_appearance_mode("light")
    App(cfg).mainloop()


if __name__ == "__main__":
    main()
