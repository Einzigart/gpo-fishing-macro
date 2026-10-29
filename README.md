# GPO Fishing Macro (macOS)

A fishing macro for Grand Piece Online on macOS. It only reads the screen and
sends normal mouse clicks and key presses. It does not inject code into Roblox
or read game memory.

## Setup

1. Install Python 3.12 from python.org if `Setup.command` says no Python is usable.
2. Double-click `Setup.command`. It builds a private `.venv` and installs the packages.
3. Grant Terminal these permissions under System Settings > Privacy & Security:
   Accessibility, Input Monitoring, Screen Recording. Quit Terminal (Cmd-Q) after.
4. Double-click `Launch.command` to open the app.

## First run

1. In GPO, equip the rod. The Fishing Baits panel appears.
2. Optional check: fish once by hand and press **Test detection** while the two bars
   show. A cyan box must sit on the dark gap and a magenta line on the fish.
3. Under Bait, tick the baits to use (Common, Rare and Legendary Fish Bait, from the
   GPO wiki) and set their order with the arrows. For each ticked bait, press
   **Pick spot** and click its row in the Fishing Baits panel. The app reads each
   count ("x296") from the panel at start and after each fish, and uses the ticked
   baits top to bottom. It keeps the last one of each bait. When every ticked bait
   is down to 1, fishing stops and the app goes anti-AFK: once a minute it casts and
   reels straight back in, so Roblox does not kick you. If a count can't be read,
   the log says why, the count shows as unknown, and the app keeps fishing with
   that bait until a read works.
   Spots are fixed screen positions, and the panel rows move when you gain a new
   bait type or one runs out completely. Own at least 1 of all 3 baits (GPO has only
   these 3), so the panel always shows the same 3 rows.
   Each read also checks the bait name on the row; if a spot shows another bait, the
   app stops and asks you to re-pick the spots.
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
When you stop, the log shows the session total per rarity.

## Hotkeys

| Key | Action |
| --- | --- |
| F1 | Start or stop fishing |
| F3 | Quit |

## Files

- `config.json` holds your settings. Delete it to go back to the defaults.
- `run-log.txt` holds the run log. Send it with `diagnose-log.txt` (from
  `Diagnose.command`) when you report a problem.

## Tests

```bash
.venv/bin/python -m unittest discover tests
```
