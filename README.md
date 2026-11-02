# GPO Fishing Macro

A fishing macro for Grand Piece Online on macOS and Windows. It reads the screen
and sends normal clicks and key presses. It does not touch Roblox's code or memory.

The Windows version is not tested on a Windows PC yet. Please report what works.

Download the zip for your system from
[Releases](https://github.com/Einzigart/gpo-fishing-macro/releases), unzip it, and
keep the files together in one folder.

## Setup on macOS

1. Install Python 3.12 from [python.org](https://www.python.org/downloads/).
2. Double-click `Setup.command`.
3. Double-click `GPO Fishing Macro.app`.
4. Allow Accessibility, Input Monitoring and Screen Recording for GPO Fishing Macro
   under System Settings > Privacy & Security. Press F3, then open the app again.

Keep the app in this folder. To start it from the Dock, make an alias of it.

## Setup on Windows

1. Install Python 3.12 from [python.org](https://www.python.org/downloads/windows/).
   Tick "Add python.exe to PATH" in the installer.
2. Double-click `Setup.bat`. It makes a `GPO Fishing Macro` shortcut.
3. Double-click the shortcut.

Run Roblox normally, not as administrator. The macro needs the English (United
States) language in Windows settings to read text.

## Use

1. In GPO, equip the rod so the Fishing Baits panel shows.
2. Under Bait, tick the baits to use and order them with the arrows.
3. Optional: press **Test detection** while the fishing bars show. A cyan box should
   sit on the gap and a magenta line on the fish.
4. Press **F1** to start and stop. **F3** quits.

What the macro does:

- Finds your baits in the panel and uses the ticked ones top to bottom. It keeps the
  last one of each.
- When every ticked bait is down to 1, it goes anti-AFK: it casts and reels in once
  a minute, so Roblox doesn't kick you.
- With **Buy Common Fish Bait** ticked and the seller next to you, it buys Common
  bait instead. **Test buy** tries one purchase.
- With **Use Buso Haki** ticked, it presses J after a catch, at most once a minute.
- Logs each catch with its rarity and keeps totals. **Catches…** shows them.
- Quits Roblox and itself when Roblox shows "Disconnected".

## Files

- `config.json`: your settings. Delete it to reset.
- `catches.csv`: every catch. Delete it to start a new history.
- `run-log.txt` and `app-log.txt`: logs.

To report a problem, run `Diagnose.command` (macOS) or `Diagnose.bat` (Windows) and
send `diagnose-log.txt` and `run-log.txt`.

## Development

Run the tests and the linter:

```bash
.venv/bin/python -m unittest discover tests
```

```bash
uvx ruff check src tests
```

On Windows, the test command is `.venv\Scripts\python -m unittest discover tests`.

Code that differs per system sits in pairs: `focus_mac.py`/`focus_win.py`,
`input_mac.py`/`input_win.py` and `ocr_mac.py`/`ocr_win.py`.

To publish a release, open the Actions tab, pick **Release**, click
**Run workflow**, and enter a version such as `v1.1.0`. It builds a macOS zip and
a Windows zip with `scripts/make_release.sh`.
