#!/bin/bash
cd "$(dirname "$0")" || exit 1

xattr -d -r com.apple.quarantine . >/dev/null 2>&1
chmod +x ./*.command src/*.sh >/dev/null 2>&1

source src/find_python.sh || { echo ""; read -n 1 -s -r -p "  press any key to close"; exit 1; }

"$PY" src/bootstrap.py main.py --check
rc=$?
echo ""
if [ $rc -ne 0 ]; then
    echo "  Setup did not finish. See the messages above and setup-log.txt."
    echo "  If it is not obvious, run Diagnose.command and send diagnose-log.txt."
else
    echo "  Setup finished. Start the macro with Launch.command."
fi
echo ""
read -n 1 -s -r -p "  press any key to close"
