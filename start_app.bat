@echo off
cd /d "%~dp0"
echo Starting OutreachAI...
echo.
"venv\Scripts\python.exe" -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
pause
