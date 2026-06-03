@echo off
REM ── NEXRAD Radar — double-click launcher ──────────────────────────────
cd /d "%~dp0"
echo Starting NEXRAD Radar...
python main.py
if errorlevel 1 (
  echo.
  echo Failed to start. Make sure dependencies are installed:
  echo     pip install -r requirements.txt
  echo.
  pause
)
