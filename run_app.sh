#!/usr/bin/env bash
# Bootstraps the venv (first run only) and launches the Siratek WeAct 0.96"
# Display Controller on Linux/macOS.
set -e
cd "$(dirname "${BASH_SOURCE[0]}")"

PYTHON="${PYTHON:-python3}"

if [ ! -f ".venv/bin/python" ]; then
    echo "Setting up virtual environment, first run only..."
    "$PYTHON" -m venv .venv
    ".venv/bin/python" -m pip install --upgrade pip
    ".venv/bin/python" -m pip install -r requirements.txt
fi

".venv/bin/python" run_app.py
