# GPO Fishing Macro (macOS and Windows)

A fishing macro for Grand Piece Online on macOS and Windows. It only reads the
screen and sends normal mouse clicks and key presses. It does not inject code
into Roblox or read game memory.

The Windows version is new and has not been tested on a Windows PC yet. Its
text reading uses Windows OCR, not Apple's Vision, so bait counts and catch
names may read differently. Run **Test detection** first and send `run-log.txt`
if the counts or names come out wrong.

## Setup on macOS

1. Install Python 3.12 from python.org if `Setup.command` says no Python is usable.
2. Double-click `Setup.command`. It builds a private `.venv`, installs the packages,
   and clears the download quarantine, so macOS lets the app open.
3. Double-click `GPO Fishing Macro.app` to start the macro. No Terminal window opens.
4. On the first start, macOS asks for three permissions for GPO Fishing Macro:
   Accessibility, Input Monitoring, Screen Recording. Turn it on in each list under
   System Settings > Privacy & Security, press F3 to quit the macro, and open the
   app again.

Keep the app in this folder: it runs the macro files next to it. To start it from
the Dock or Applications, make an alias there (hold Option and Command while you
drag the app). If setup is missing or the packages changed, the app opens
`Setup.command` for you. If the macro ends with an error, the app shows a dialog
and writes the details to `app-log.txt`.

`Launch.command` still works and starts the macro from Terminal. Permissions are
granted per app, so that way needs them for Terminal instead.

## Setup on Windows

1. Install Python 3.12 from python.org (the "Windows installer (64-bit)"). In the
   installer, tick "Add python.exe to PATH" and keep "py launcher" and "tcl/tk" on.
2. Double-click `Setup.bat`. It builds a private `.venv`, installs the packages, and
   makes a `GPO Fishing Macro` shortcut with the fish icon in this folder.
3. Double-click the `GPO Fishing Macro` shortcut. No console window opens. To start
   it from the desktop or Start, copy the shortcut there or pin it to Start.

Windows needs no permissions for the macro. Two things can still block it:

- Run Roblox normally, not as administrator. Windows blocks clicks and key presses
  from a normal program into a program that runs as administrator.
- The macro reads text with Windows OCR, which needs the English (United States)
  language under Settings > Time & language > Language & region. Most Windows PCs
  have it. If not, the run stops and says so.

If setup is missing or the packages changed, the shortcut offers to run
`Setup.bat`. If the macro ends with an error, it shows a dialog and writes the
details to `app-log.txt`. `Launch.bat` starts the macro with a console window, so
you can see its output. `Diagnose.bat` writes `diagnose-log.txt` for bug reports.

## First run

1. In GPO, equip the rod. The Fishing Baits panel appears.
2. Optional check: fish once by hand and press **Test detection** while the two bars
   show. A cyan box must sit on the dark gap and a magenta line on the fish.
3. The app finds the baits by itself: it reads the names in the game's Fishing Baits
   panel row by row, so there is nothing to pick, and baits you have none of are
   skipped. The panel shows only the baits you own, so the app reads it again
   whenever the rows may have moved, for example after buying Common bait.
   Under Bait, tick the baits to use and set their order with the arrows. The app
   reads each count ("x296") at start and after each fish, and uses the ticked baits
   top to bottom. It keeps the last one of each bait. When every ticked bait is down
   to 1, fishing stops and the app goes anti-AFK: once a minute it casts and reels
   straight back in, so Roblox does not kick you.
   If the panel isn't showing at start (rod not equipped), the app stops and says so.
   After each bait click, the app checks the game's gold "selected" frame on that
   row; if the bait still isn't selected after a second click, it stops before
   casting, so it never uses the last bait of another type. Each count is read up to
   5 times. One read is enough when it shows the count the app expects (one less, or
   the same); any other count must read the same twice. A count of 1 ends that bait,
   so it needs 2 equal reads, or 3 when it was not expected. If a count can't be read
   mid-run, the log says why, the count shows as unknown, and the app keeps fishing
   with that bait until a read works.
4. Optional: tick **Buy Common Fish Bait when all bait is down to 1** and stand next
   to the Common Fish Bait seller. When every ticked bait is down to 1, the app presses
   E, clicks Yes, types the MAX amount, clicks Buy and closes the dialog, then keeps
   fishing with Common Fish Bait. If the purchase fails, the log says why and the app
   goes anti-AFK.
   To try the purchase once, stand next to the seller and press **Test buy**. The
   status line shows the result and the new Common count; F1 stops it.
5. Optional: tick **Use Buso Haki** to press J after a catch, at most once a minute.
   It also presses J during anti-AFK. Change the gaps under Tuning, "Buso Haki
   every (s)" and "Anti-AFK every (s)".
6. Optional: pick the cast spot (open water), and set the rod hotbar key.
7. Press **F1** to start and stop.

The bars hang beside your character, so they move and scale with the camera. The
app searches the whole Roblox window for them, so camera moves and zoom do not
matter. Keep the app's own windows off the game while it runs; the app minimizes
any that cover it.

If Roblox shows its "Disconnected" dialog, the app force-quits Roblox and then quits
itself. It checks after each cast with no bite and each anti-AFK round.

After each fish, the app reads the "New Item <name>" banner and logs the catch with
its rarity, for example "Caught Blue-Lip Grouper (Common)." A banner always counts as
a catch. For the fish and items the GPO wiki lists, the app uses the wiki name and
rarity, which also fixes small misreads. For anything else, the rarity comes from the
name colour: green is Common, teal is Rare, lavender is Epic, and rainbow is Legendary.
Any other colour (fruits, for example) is logged as "unknown (<colour>)".

Under the counters, the app shows the session total per rarity. Each catch is also
saved to `catches.csv`, so the history lasts between runs. Press **Catches…** to see
the session totals, the all-time totals per rarity, and how often you caught each
fish or item. A catch whose name could not be read is saved as "(name not read)".

## Hotkeys

| Key | Action |
| --- | --- |
| F1 | Start or stop fishing |
| F3 | Quit |

## Files

- `config.json` holds your settings. Delete it to go back to the defaults.
- `catches.csv` holds every catch (time, name, rarity). Delete it to start a new history.
- `run-log.txt` holds the run log. Send it with `diagnose-log.txt` (from
  `Diagnose.command` or `Diagnose.bat`) when you report a problem.
- `app-log.txt` holds the output of the last start from the app or the Windows
  shortcut, including errors.
- `assets/app-icon.svg` is the source of the app icon. The macOS app uses
  `GPO Fishing Macro.app/Contents/Resources/AppIcon.icns`; the Windows shortcut
  uses `assets/app-icon.ico`.

The code that differs per system sits in pairs: `focus_mac.py` and
`focus_win.py` (find and focus the Roblox window), `input_mac.py` and
`input_win.py` (mouse and keys), `ocr_mac.py` and `ocr_win.py` (text recognition).
Screen capture uses CoreGraphics on macOS (`mac_grab.py`) and mss on Windows.

## Releases

Each release on GitHub has a macOS zip and a Windows zip, built from the
committed files by `scripts/make_release.sh`. To publish one, open the Actions
tab, pick **Release**, click **Run workflow**, and enter a version such as
`v1.1.0`. Pushing a tag that starts with `v` does the same. The download steps
shown on the release page come from `.github/release-notes.md`.

## Tests

```bash
.venv/bin/python -m unittest discover tests
```

On Windows:

```bat
.venv\Scripts\python -m unittest discover tests
```

The text-reading tests on the screenshots in `tests/fixtures` were tuned with
Vision. On Windows they show how well Windows OCR reads the same pictures.

Lint with ruff (its default rules, at the 120-column width in `ruff.toml`):

```bash
uvx ruff check src tests
```
