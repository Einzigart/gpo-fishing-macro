#!/bin/bash
cd "$(dirname "$0")" || exit 1

xattr -d -r com.apple.quarantine . >/dev/null 2>&1
chmod +x ./*.command src/*.sh "GPO Fishing Macro.app/Contents/MacOS/launch" >/dev/null 2>&1
# Finder caches app icons; a new date on the bundle makes it show the fish icon.
touch "GPO Fishing Macro.app" >/dev/null 2>&1

source src/find_python.sh || { echo ""; read -n 1 -s -r -p "  press any key to close"; exit 1; }

"$PY" src/bootstrap.py main.py --check
rc=$?
echo ""
if [ $rc -ne 0 ]; then
    echo "  Setup did not finish. See the messages above and setup-log.txt."
    echo "  If it is not obvious, run Diagnose.command and send diagnose-log.txt."
else
    echo "  Setup finished. Open GPO Fishing Macro.app to start the macro"
    echo "  (Launch.command still works too)."
fi
echo ""
read -n 1 -s -r -p "  press any key to close"
