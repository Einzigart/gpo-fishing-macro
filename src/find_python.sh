PY=""
PY_SEEN=""

_note_seen() {
    ver="$("$1" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)"
    [ -z "$ver" ] && return 0
    PY_SEEN="$PY_SEEN
      $1  (Python $ver)  $2"
}

try_python() {
    [ -x "$1" ] || return 0
    if ! "$1" -c 'import sys; sys.exit(0 if (3, 10) <= sys.version_info < (3, 15) else 1)' >/dev/null 2>&1; then
        _note_seen "$1" "- too old or too new, needs 3.10-3.14"
        return 0
    fi
    if ! "$1" -c 'import venv' >/dev/null 2>&1; then
        _note_seen "$1" "- no venv module"
        return 0
    fi
    if ! "$1" -c 'import tkinter' >/dev/null 2>&1; then
        _note_seen "$1" "- no tkinter, install Python from python.org"
        return 0
    fi
    PY="$1"
}

for v in 3.12 3.11 3.10 3.13 3.14; do
    [ -z "$PY" ] && try_python "/Library/Frameworks/Python.framework/Versions/$v/bin/python3"
done
for v in 3.12 3.11 3.10 3.13 3.14; do
    for d in /opt/homebrew/bin /usr/local/bin; do
        [ -z "$PY" ] && try_python "$d/python$v"
    done
done
for c in /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    [ -z "$PY" ] && try_python "$c"
done

for n in python3.12 python3.11 python3.10 python3.13 python3.14 python3; do
    if [ -z "$PY" ]; then
        c="$(command -v "$n" 2>/dev/null)"
        case "$c" in
            "") ;;
            /usr/bin/python3) ;;
            *) try_python "$c" ;;
        esac
    fi
done

if [ -z "$PY" ]; then
    echo ""
    echo "  No usable Python was found on this Mac."
    echo ""
    echo "  This macro needs Python 3.10 to 3.14 (3.12 is the safest,"
    echo "  and the only one that works on every macOS from 11 Big Sur up)."
    echo ""
    echo "  Install Python 3.12 from"
    echo "      https://www.python.org/downloads/release/python-3128/"
    echo "  Pick 'macOS 64-bit universal2 installer', then run this again."
    if [ -n "$PY_SEEN" ]; then
        echo ""
        echo "  Found but not usable:$PY_SEEN"
    fi
    echo ""
    return 1
fi
return 0
