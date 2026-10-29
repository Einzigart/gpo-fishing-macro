#!/bin/bash
cd "$(dirname "$0")" || exit 1

xattr -d -r com.apple.quarantine . >/dev/null 2>&1
chmod +x ./*.command src/*.sh >/dev/null 2>&1

hold() {
    echo ""
    read -n 1 -s -r -p "  press any key to close"
    echo ""
}

source src/find_python.sh || { hold; exit 1; }

"$PY" src/bootstrap.py main.py
rc=$?
if [ $rc -ne 0 ]; then
    echo ""
    echo "  The macro exited with an error (code $rc)."
    echo "  Run Diagnose.command and send the diagnose-log.txt it writes."
    hold
fi
exit $rc
