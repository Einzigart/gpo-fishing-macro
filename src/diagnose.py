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
    except Exception as exc:
        return "(failed: %s)" % exc


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
    out("macOS            : %s" % platform.mac_ver()[0])
    out("sw_vers          : %s" % sh(["sw_vers", "-productVersion"]))
    out("build            : %s" % sh(["sw_vers", "-buildVersion"]))
    out("arch (uname -m)  : %s" % sh(["uname", "-m"]))
    out("arch (python)    : %s" % platform.machine())
    out("running under    : %s" % sys.executable)

    ver = platform.mac_ver()[0].split(".")
    try:
        major = int(ver[0])
    except (ValueError, IndexError):
        major = 0
    if major and major < 11:
        out("")
        out("!! This Mac is older than macOS 11. This build targets 11+.")

    section("Folder")
    out("location         : %s" % ROOT)
    q = sh(["xattr", "-l", os.path.join(ROOT, "Launch.command")])
    out("Launch.command   : %s" % ("quarantined -- %s" % q if "quarantine" in q
                                   else "not quarantined"))

    section("Pythons on this Mac")
    cands = candidate_pythons()
    if not cands:
        out("none found")
    usable = []
    for path, real in cands:
        info = probe(path)
        out("%-58s %s" % (path, info))
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
        out("python           : %s" % sh([VENV_PY, "-V"]))
        out("")
        for mod in NEEDED:
            r = sh([VENV_PY, "-c",
                    "import %s as m; print(getattr(m,'__version__','ok'))" % mod])
            first = r.splitlines()[-1] if r else "(no output)"
            ok = "ok" if "Error" not in r and "Traceback" not in r else "FAILED"
            out("  %-20s %-8s %s" % (mod, ok, first if ok == "ok" else r[:400]))

    section("Permissions")
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

    out()
    out("end of diagnostic")


if __name__ == "__main__":
    main()
