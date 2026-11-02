"""Print system, Python, package and permission facts to diagnose-log.txt."""
import glob
import os
import platform
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WINDOWS = sys.platform == "win32"
VENV_PY = (os.path.join(ROOT, ".venv", "Scripts", "python.exe") if WINDOWS
           else os.path.join(ROOT, ".venv", "bin", "python3"))
SETUP = "Setup.bat" if WINDOWS else "Setup.command"

NEEDED = ["cv2", "numpy", "mss", "pynput", "customtkinter"] + (
    ["winrt.windows.media.ocr", "winrt.windows.graphics.imaging", "winrt.windows.storage.streams",
     "winrt.windows.globalization"] if WINDOWS
    else ["Quartz", "AppKit", "ApplicationServices", "Vision"])


def out(msg=""):
    print(msg)


def sh(args):
    try:
        p = subprocess.Popen(args, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
        return p.communicate()[0].decode("utf-8", "replace").strip()
    except Exception as exc:  # noqa: BLE001 -- a diagnostic report keeps going and shows the failure
        return f"(failed: {exc})"


def section(title):
    out()
    out(title)
    out("-" * len(title))


def candidate_pythons():
    if WINDOWS:
        return windows_pythons()
    seen = []
    for pat in ["/Library/Frameworks/Python.framework/Versions/*/bin/python3",
                "/opt/homebrew/bin/python3*", "/usr/local/bin/python3*",
                "/usr/bin/python3"]:
        for path in sorted(glob.glob(pat)):
            if path.endswith("-config"):
                continue
            if os.path.isfile(path) and os.access(path, os.X_OK):
                real = os.path.realpath(path)
                if real not in [r for _, r in seen]:
                    seen.append((path, real))
    return seen


def windows_pythons():
    """Every Python the py launcher knows ("py -0p"), plus python.exe on PATH."""
    seen = []
    listing = sh(["py", "-0p"])
    paths = re.findall(r"([A-Za-z]:\\\S.*?python[w]?\.exe)", listing, re.IGNORECASE)
    paths += sh(["where", "python"]).splitlines()
    for path in paths:
        path = path.strip()
        if path.lower().endswith(".exe") and os.path.isfile(path):
            real = os.path.realpath(path)
            if "windowsapps" in real.lower():
                continue  # the Microsoft Store stub, which only opens the Store
            if real not in [r for _, r in seen]:
                seen.append((path, real))
    return seen


def probe(path):
    code = ("import sys;"
            "v='%d.%d.%d' % sys.version_info[:3];"
            "\ntry:\n import tkinter; tk='tkinter ok'\nexcept Exception: tk='NO tkinter'"
            "\ntry:\n import venv; ve='venv ok'\nexcept Exception: ve='NO venv'"
            "\nprint(v+' | '+tk+' | '+ve)")
    return sh([path, "-c", code])


def system_mac():
    out(f"macOS            : {platform.mac_ver()[0]}")
    out("sw_vers          : {}".format(sh(["sw_vers", "-productVersion"])))
    out("build            : {}".format(sh(["sw_vers", "-buildVersion"])))
    out("arch (uname -m)  : {}".format(sh(["uname", "-m"])))
    out(f"arch (python)    : {platform.machine()}")
    out(f"running under    : {sys.executable}")

    ver = platform.mac_ver()[0].split(".")
    try:
        major = int(ver[0])
    except (ValueError, IndexError):
        major = 0
    if major and major < 11:
        out("")
        out("!! This Mac is older than macOS 11. This build targets 11+.")

    section("Folder")
    out(f"location         : {ROOT}")
    q = sh(["xattr", "-l", os.path.join(ROOT, "Launch.command")])
    out("Launch.command   : %s" % (f"quarantined -- {q}" if "quarantine" in q
                                   else "not quarantined"))
    app = os.path.join(ROOT, "GPO Fishing Macro.app")
    launcher = os.path.join(app, "Contents", "MacOS", "launch")
    if os.path.isdir(app):
        q = sh(["xattr", "-l", app])
        state = f"quarantined -- {q}" if "quarantine" in q else "not quarantined"
        runs = "executable" if os.access(launcher, os.X_OK) else "NOT executable (run Setup.command)"
        out(f"app              : {state}, launcher {runs}")
    else:
        out("app              : missing")


def system_windows():
    out(f"Windows          : {platform.platform()}")
    out(f"version          : {platform.version()}")
    out(f"arch (python)    : {platform.machine()}")
    out(f"running under    : {sys.executable}")

    section("Folder")
    out(f"location         : {ROOT}")
    lnk = os.path.join(ROOT, "GPO Fishing Macro.lnk")
    out("shortcut         : {}".format("present" if os.path.exists(lnk) else "missing (run Setup.bat)"))


def permissions_mac():
    section("Permissions")
    out("(These are Terminal's. GPO Fishing Macro.app has its own set.)")
    if not os.path.exists(VENV_PY):
        out("(needs .venv -- run Setup.command first)")
        return
    code = ("\ntry:\n"
            "    import Quartz\n"
            "    print('Screen Recording :', bool(Quartz.CGPreflightScreenCaptureAccess()))\n"
            "    print('Input Monitoring :', bool(Quartz.CGPreflightListenEventAccess()))\n"
            "except Exception as e:\n"
            "    print('Quartz check failed:', e)\n"
            "try:\n"
            "    from ApplicationServices import AXIsProcessTrusted\n"
            "    print('Accessibility    :', bool(AXIsProcessTrusted()))\n"
            "except Exception as e:\n"
            "    print('Accessibility check failed:', e)\n")
    out(sh([VENV_PY, "-c", code]))


def text_recognition_windows():
    section("Text recognition")
    if not os.path.exists(VENV_PY):
        out("(needs .venv -- run Setup.bat first)")
        return
    code = ("\ntry:\n"
            "    from winrt.windows.globalization import Language\n"
            "    from winrt.windows.media.ocr import OcrEngine\n"
            "    langs = [l.language_tag for l in OcrEngine.available_recognizer_languages]\n"
            "    print('OCR languages    :', ', '.join(langs) or 'NONE -- add English in Language settings')\n"
            "    print('English (en-US)  :', OcrEngine.try_create_from_language(Language('en-US')) is not None)\n"
            "except Exception as e:\n"
            "    print('OCR check failed:', e)\n")
    out(sh([VENV_PY, "-c", code]))


def main():
    out("gpo-fishing-macro diagnostic")
    out("=" * 28)

    section("System")
    if WINDOWS:
        system_windows()
    else:
        system_mac()

    section("Pythons on this " + ("PC" if WINDOWS else "Mac"))
    cands = candidate_pythons()
    if not cands:
        out("none found")
    usable = []
    for path, real in cands:
        info = probe(path)
        out(f"{path:<58} {info}")
        parts = info.split(".")
        try:
            if (3, 10) <= (int(parts[0]), int(parts[1])) < (3, 15) and \
               "NO" not in info:
                usable.append(path)
        except (ValueError, IndexError):
            pass
    out("")
    out("usable (3.10-3.14, with tkinter and venv): %s"
        % (", ".join(usable) if usable else "NONE -- this is the problem"))

    section("Virtual environment")
    if not os.path.exists(VENV_PY):
        out(f".venv not built yet (run {SETUP})")
    else:
        out("python           : {}".format(sh([VENV_PY, "-V"])))
        out("")
        for mod in NEEDED:
            r = sh([VENV_PY, "-c",
                    f"import {mod} as m; print(getattr(m,'__version__','ok'))"])
            first = r.splitlines()[-1] if r else "(no output)"
            ok = "ok" if "Error" not in r and "Traceback" not in r else "FAILED"
            out(f"  {mod:<20} {ok:<8} {first if ok == 'ok' else r[:400]}")

    if WINDOWS:
        text_recognition_windows()
    else:
        permissions_mac()

    section("Tail of setup-log.txt")
    log = os.path.join(ROOT, "setup-log.txt")
    if os.path.exists(log):
        with open(log, "r") as fh:
            tail = fh.read()[-3000:]
        out(tail)
    else:
        out("(no setup-log.txt)")

    section("Tail of app-log.txt")
    log = os.path.join(ROOT, "app-log.txt")
    if os.path.exists(log):
        with open(log, "r", errors="replace") as fh:
            out(fh.read()[-3000:])
    else:
        out("(no app-log.txt; the app was not opened yet)")

    out()
    out("end of diagnostic")


if __name__ == "__main__":
    main()
