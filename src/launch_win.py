"""Start the macro on Windows with no console window (run by pythonw.exe).

The "GPO Fishing Macro" shortcut that Setup.bat makes points here. Like the
macOS app launcher: output goes to app-log.txt, a missing or stale setup
opens Setup.bat, and an error at startup shows a dialog.
"""
from __future__ import annotations

import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOG = os.path.join(ROOT, "app-log.txt")
NAME = "GPO Fishing Macro"


def _alert(message: str, yes_no: bool = False) -> bool:
    """A dialog without the app window. True when the user clicked Yes (or OK)."""
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    try:
        if yes_no:
            return bool(messagebox.askyesno(NAME, message, parent=root))
        messagebox.showerror(NAME, message, parent=root)
        return True
    finally:
        root.destroy()


def _setup_needed() -> bool:
    import bootstrap

    if not os.path.exists(bootstrap.STAMP):
        return True
    with open(bootstrap.STAMP) as f:
        return f.read().strip() != bootstrap.requirements_hash()


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, HERE)
    # pythonw has no console: sys.stdout and sys.stderr are None.
    with open(LOG, "w", encoding="utf-8", errors="replace", buffering=1) as log:
        sys.stdout = sys.stderr = log
        return _run()


def _run() -> int:
    print(f"=== {time.strftime('%Y-%m-%d %H:%M:%S')} {NAME} started with {sys.executable}")
    if _setup_needed():
        print("Setup is needed: the packages are missing or changed.")
        if _alert("The macro is not set up yet, or its packages changed. Run Setup.bat now?\n\n"
                  "When it finishes, open GPO Fishing Macro again.", yes_no=True):
            os.startfile(os.path.join(ROOT, "Setup.bat"))
        return 0
    try:
        import main as app

        app.main()
    except SystemExit as exc:
        return int(exc.code or 0) if isinstance(exc.code, int) else 1
    except Exception:  # noqa: BLE001 -- any startup error goes to the log and a dialog
        traceback.print_exc()
        if _alert(f"The macro stopped with an error:\n\n{traceback.format_exc(limit=1).strip()}\n\n"
                  "The details are in app-log.txt. Open it now?", yes_no=True):
            os.startfile(LOG)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
