Download the zip for your system from **Assets** below, and unzip it. Keep all the files together in one folder.

## macOS: `GPO-Fishing-Macro-…-macOS.zip`

1. Install Python 3.12 from [python.org](https://www.python.org/downloads/) if you don't have it.
2. Double-click `Setup.command`. macOS blocks it the first time because it comes from the internet:
   - macOS 15 and later: open System Settings > Privacy & Security, scroll down, and click **Open Anyway** next to Setup.command.
   - macOS 14 and earlier: right-click `Setup.command`, choose **Open**, then **Open** again.
3. When setup finishes, double-click `GPO Fishing Macro.app`.
4. Allow Accessibility, Input Monitoring and Screen Recording for GPO Fishing Macro when macOS asks, press F3, and open the app again.

## Windows: `GPO-Fishing-Macro-…-Windows.zip`

The Windows version has not been tested on a Windows PC yet. Please report what works and what doesn't.

1. Before you unzip, right-click the zip, choose **Properties**, tick **Unblock**, and click OK. Then unzip it.
2. Install Python 3.12 from [python.org](https://www.python.org/downloads/windows/). Tick "Add python.exe to PATH" in the installer.
3. Double-click `Setup.bat`. If Windows shows "Windows protected your PC", click **More info**, then **Run anyway**.
4. Double-click the `GPO Fishing Macro` shortcut that setup made.

Run Roblox normally, not as administrator. The macro reads text with Windows OCR, which needs the English (United States) language in Windows settings.

## Both

Press F1 to start and stop fishing, F3 to quit. See `README.md` in the zip for the full guide. To report a problem, run `Diagnose.command` (macOS) or `Diagnose.bat` (Windows) and send `diagnose-log.txt` and `run-log.txt`.
