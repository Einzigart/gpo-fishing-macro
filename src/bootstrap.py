"""Build the private .venv, install requirements once, then run the app.

Usage: python bootstrap.py main.py [--check] [--no-install]
--check installs and prints the macOS permission notes without starting the app.
--no-install exits with NOT_SET_UP instead of building .venv or installing
packages. The .app uses it: it has no window to show a long install in.
"""
import hashlib
import importlib
import os
import platform
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VENV = os.path.join(ROOT, ".venv")
VENV_PY = os.path.join(VENV, "bin", "python3")
STAMP = os.path.join(VENV, ".requirements-stamp")
LOG = os.path.join(ROOT, "setup-log.txt")
REQUIREMENTS = os.path.join(HERE, "requirements.txt")
NOT_SET_UP = 78
MUST_IMPORT = ["cv2", "numpy", "mss", "pynput", "Quartz", "AppKit", "ApplicationServices", "Vision", "customtkinter"]


def say(msg):
    print(" " + msg, flush=True)


def requirements_hash():
    with open(REQUIREMENTS, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def run(args, **kw):
    return subprocess.call(args, cwd=ROOT, **kw)


def run_logged(args):
    with open(LOG, "a", encoding="utf-8", errors="replace") as log:
        log.write("\n$ " + " ".join(args) + "\n")
        log.flush()
        proc = subprocess.Popen(args, cwd=ROOT, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        for raw in proc.stdout:
            line = raw.decode("utf-8", "replace")
            sys.stdout.write(line)
            sys.stdout.flush()
            log.write(line)
        return proc.wait()


def tk_ok():
    try:
        importlib.import_module("tkinter")
        return True
    except ImportError:
        return False


def explain_failure():
    v = sys.version_info
    say("")
    say("Install failed. The full output is in setup-log.txt next to Launch.command.")
    say(f"Python {v.major}.{v.minor}.{v.micro} at {sys.executable} on macOS {platform.mac_ver()[0]}"
        f" ({platform.machine()})")
    say("")
    if v >= (3, 13):
        say(f"* This is Python {v.major}.{v.minor}. Older Macs (macOS 11 on Intel especially) have")
        say("  no package builds for 3.13+. Install Python 3.12 from")
        say("      https://www.python.org/downloads/release/python-3128/")
        say("  delete the .venv folder, and run Setup.command again; it prefers 3.12.")
    say("* If the log ends in a download or SSL error, that one really is the")
    say("  connection, a proxy, or a firewall.")
    say("")
    say("Run Setup.command to try again; send setup-log.txt if it still fails.")


def ensure_venv():
    if os.path.exists(VENV_PY):
        return True
    say("Building a private Python environment in .venv (one-time, ~20s)...")
    code = run_logged([sys.executable, "-m", "venv", VENV])
    if code != 0 or not os.path.exists(VENV_PY):
        say("Could not create .venv. See setup-log.txt next to Launch.command.")
        return False
    return True


def packages_ok():
    if not os.path.exists(STAMP):
        return False
    with open(STAMP) as f:
        if f.read().strip() != requirements_hash():
            return False
    probe = "import " + ", ".join(MUST_IMPORT)
    return run([VENV_PY, "-c", probe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0


def install_packages():
    say("Installing packages (one-time, a minute or two)...")
    print(flush=True)
    run_logged([VENV_PY, "-m", "pip", "install", "--upgrade", "pip", "--quiet",
                "--disable-pip-version-check"])
    code = run_logged([VENV_PY, "-m", "pip", "install", "-r", REQUIREMENTS,
                       "--only-binary=:all:", "--disable-pip-version-check"])
    print(flush=True)
    if code != 0:
        explain_failure()
        return False
    probe = "import " + ", ".join(MUST_IMPORT)
    if run_logged([VENV_PY, "-c", probe]) != 0:
        say("Packages installed but something will not import. See setup-log.txt.")
        return False
    with open(STAMP, "w") as f:
        f.write(requirements_hash())
    say("Packages installed.")
    return True


def platform_notes():
    ver = platform.mac_ver()[0]
    say(f"macOS {ver} detected.")
    say("")
    say("The first run asks for three permissions:")
    say("    Accessibility, Input Monitoring, Screen Recording")
    say("They go to what starts the macro: GPO Fishing Macro when you open the")
    say("app, or Terminal when you use Launch.command.")
    say("")
    if ver.split(".")[0] in ("11", "12"):
        say("On macOS {} they are under:".format(ver.split(".")[0]))
        say("    System Preferences > Security & Privacy > Privacy")
        say("Click the padlock at the bottom left to unlock it first.")
    else:
        say("    System Settings > Privacy & Security")
    say("")
    say("Turn it on in all three lists, then quit it completely (F3 for the app,")
    say("Cmd-Q for Terminal) and start the macro again.")


def main():
    args = sys.argv[1:]
    no_install = "--no-install" in args
    args = [a for a in args if a != "--no-install"]
    if os.path.exists(LOG):
        os.remove(LOG)
    if not tk_ok():
        say("This Python has no tkinter (the window toolkit).")
        say("Install Python from python.org; it ships with tkinter.")
        return 1
    if no_install and not (os.path.exists(VENV_PY) and packages_ok()):
        say("Setup is needed: run Setup.command.")
        return NOT_SET_UP
    if not ensure_venv():
        return 1
    if not packages_ok() and not install_packages():
        return 1
    if os.path.exists(LOG):
        os.remove(LOG)
    script = "main.py"
    if args and args[0].endswith(".py"):
        script, args = args[0], args[1:]
    if args and args[0] == "--check":
        platform_notes()
        return 0
    return run([VENV_PY, os.path.join(HERE, script)] + args)


if __name__ == "__main__":
    sys.exit(main())
