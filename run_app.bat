@echo off
REM Bootstraps the venv (first run only) and launches the WeAct display app.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Setting up virtual environment, first run only...
    python -m venv .venv
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

".venv\Scripts\python.exe" run_app.py
pause
