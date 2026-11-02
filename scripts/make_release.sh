#!/bin/bash
# Build the release zips from the committed files: one for macOS, one for
# Windows. Usage: scripts/make_release.sh v1.0.0  (writes dist/*.zip)
# git archive applies .gitattributes, so the batch files get CRLF and the
# shell scripts keep LF and their executable bit.
set -euo pipefail
VERSION="${1:?usage: make_release.sh <version>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
rm -rf dist && mkdir -p dist/stage

pack() {  # pack <name> <paths...>
    local name="$1"; shift
    git archive --format=tar --prefix="$name/" HEAD -- "$@" | tar -x -C dist/stage
    (cd dist/stage && zip -q -r -X "../$name.zip" "$name")
    echo "dist/$name.zip"
}

# Each zip leaves out the other system's files.
pack "GPO-Fishing-Macro-$VERSION-macOS" \
    "GPO Fishing Macro.app" Setup.command Launch.command Diagnose.command src assets README.md \
    ':(exclude)src/*_win.py' ':(exclude)src/find_python.bat' ':(exclude)assets/app-icon.ico'
pack "GPO-Fishing-Macro-$VERSION-Windows" \
    Setup.bat Launch.bat Diagnose.bat src assets README.md \
    ':(exclude)src/*_mac.py' ':(exclude)src/find_python.sh'

rm -rf dist/stage
