#!/bin/bash
cd "$(dirname "$0")" || exit 1

xattr -d -r com.apple.quarantine . >/dev/null 2>&1
chmod +x ./*.command src/*.sh >/dev/null 2>&1

PY_DIAG=""
for c in /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
         /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 \
         /Library/Frameworks/Python.framework/Versions/3.10/bin/python3 \
         /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
         /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    [ -z "$PY_DIAG" ] && [ -x "$c" ] && PY_DIAG="$c"
done

if [ -n "$PY_DIAG" ]; then
    "$PY_DIAG" src/diagnose.py | tee diagnose-log.txt
else
    {
        echo "No Python was found on this Mac."
        echo "macOS: $(sw_vers -productVersion)  arch: $(uname -m)"
    } | tee diagnose-log.txt
fi

echo ""
echo "  Written to diagnose-log.txt next to this file. Send that file."
echo ""
read -n 1 -s -r -p "  press any key to close"
