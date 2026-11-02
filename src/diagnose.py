"""Print system, Python, package and permission facts to diagnose-log.txt."""
import glob
import os
import platform
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VENV_PY = os.path.join(ROOT, ".venv", "bin", "python3")

NEEDED = ["cv2", "numpy", "mss", "pynput", "Quartz", "AppKit",
          "ApplicationServices", "Vision", "customtkinter"]


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


def probe(path):
    code = ("import sys;"
            "v='%d.%d.%d' % sys.version_info[:3];"
            "\ntry:\n import tkinter; tk='tkinter ok'\nexcept Exception: tk='NO tkinter'"
            "\ntry:\n import venv; ve='venv ok'\nexcept Exception: ve='NO venv'"
            "\nprint(v+' | '+tk+' | '+ve)")
    return sh([path, "-c", code])


def main():
    out("gpo-fishing-macro diagnostic")
    out("=" * 28)

    section("System")
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

    section("Pythons on this Mac")
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
        out(".venv not built yet (run Setup.command)")
    else:
        out("python           : {}".format(sh([VENV_PY, "-V"])))
        out("")
        for mod in NEEDED:
            r = sh([VENV_PY, "-c",
                    f"import {mod} as m; print(getattr(m,'__version__','ok'))"])
            first = r.splitlines()[-1] if r else "(no output)"
            ok = "ok" if "Error" not in r and "Traceback" not in r else "FAILED"
            out(f"  {mod:<20} {ok:<8} {first if ok == 'ok' else r[:400]}")

    section("Permissions")
    out("(These are Terminal's. GPO Fishing Macro.app has its own set.)")
    if os.path.exists(VENV_PY):
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
    else:
        out("(needs .venv -- run Setup.command first)")

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
