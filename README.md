# GPO Fishing Macro (macOS)

A fishing macro for Grand Piece Online on macOS. It only reads the screen and
sends normal mouse clicks and key presses. It does not inject code into Roblox
or read game memory.

## Setup

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
  `Diagnose.command`) when you report a problem.
- `app-log.txt` holds the output of the last start from the app, including errors.

## Tests

```bash
.venv/bin/python -m unittest discover tests
```

Lint with ruff (its default rules, at the 120-column width in `ruff.toml`):

```bash
uvx ruff check src tests
```
