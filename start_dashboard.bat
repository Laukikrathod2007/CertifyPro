@echo off
setlocal
cd /d "%~dp0"

echo Starting Certificate Generator Dashboard...
echo Make sure you have python installed and requirements are already present.
echo.

:: Start the browser with a 2 second delay so Uvicorn has time to boot up
start /b powershell -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8002'"

:: Start the FastAPI app explicitly on IPv4
python -m uvicorn app.main:app --host 127.0.0.1 --port 8002

pause
