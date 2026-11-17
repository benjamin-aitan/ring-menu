#!/usr/bin/env bash
# Create the project virtual environment in .venv/ and install requirements.
#
# A venv does not download or install Python itself: it is a thin wrapper
# around the interpreter that created it. So this script first finds the
# project's Python version (PY_VERSION) on the machine, then builds the venv
# from that interpreter, then installs the packages into it.
#
# Usage: ./setup_venv.sh
# Override the interpreter with PYTHON, e.g. PYTHON=/path/to/python3.13 ./setup_venv.sh
# Safe to re-run: an existing .venv is reused if it already runs PY_VERSION,
# and rebuilt if it was made with a different Python.
set -euo pipefail

cd "$(dirname "$0")"

PY_VERSION="3.13"
PYTHON="${PYTHON:-python$PY_VERSION}"
VENV_DIR=".venv"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "error: '$PYTHON' not found. This project uses Python $PY_VERSION." >&2
    echo "  macOS:  brew install python@$PY_VERSION" >&2
    echo "  or point the script at it: PYTHON=/path/to/python$PY_VERSION ./setup_venv.sh" >&2
    exit 1
fi

FOUND_VERSION="$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if [ "$FOUND_VERSION" != "$PY_VERSION" ]; then
    echo "error: '$PYTHON' is Python $FOUND_VERSION, but this project uses Python $PY_VERSION." >&2
    exit 1
fi

VENV_PY="$VENV_DIR/bin/python"
# Windows (Git Bash) venvs put the interpreter in Scripts/ instead of bin/.
[ -x "$VENV_PY" ] || [ ! -x "$VENV_DIR/Scripts/python" ] || VENV_PY="$VENV_DIR/Scripts/python"

if [ -d "$VENV_DIR" ]; then
    VENV_VERSION="$("$VENV_PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "unknown")"
    if [ "$VENV_VERSION" = "$PY_VERSION" ]; then
        echo "Reusing existing Python $VENV_VERSION virtual environment in $VENV_DIR/"
    else
        echo "Existing $VENV_DIR/ uses Python $VENV_VERSION, not $PY_VERSION: rebuilding it"
        rm -rf "$VENV_DIR"
    fi
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment in $VENV_DIR/ with $("$PYTHON" --version 2>&1) ($(command -v "$PYTHON"))"
    "$PYTHON" -m venv "$VENV_DIR"
    VENV_PY="$VENV_DIR/bin/python"
    [ -x "$VENV_PY" ] || VENV_PY="$VENV_DIR/Scripts/python"
fi

echo "Upgrading pip"
"$VENV_PY" -m pip install --upgrade pip

echo "Installing requirements.txt"
# --no-compile: PySide6 ships Jinja template files named *.py that cannot be
# byte-compiled. Newer Pythons just warn, but older ones (e.g. 3.9) crash in
# compileall and abort the install. Python compiles modules on first import
# anyway, so nothing is lost.
"$VENV_PY" -m pip install --no-compile -r requirements.txt

echo "Checking install"
"$VENV_PY" -c 'import sys, PySide6, pytest; print(f"Python {sys.version.split()[0]}, PySide6 {PySide6.__version__}, pytest {pytest.__version__}")'

echo
echo "Done. Run project commands with the environment's interpreter, e.g.:"
echo "    $VENV_PY make_scenario.py"
echo "    $VENV_PY radial_menu.py"
