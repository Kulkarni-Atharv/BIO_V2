@echo off
title BIO_V2 - LAN Attendance Receiver

echo ====================================================
echo   BIO_V2  --  LAN Attendance Receiver
echo   Listening on ALL interfaces, port 8000
echo   Press Ctrl+C to stop
echo ====================================================
echo.

:: Move to project root (one folder above 'server')
cd /d "%~dp0.."

:: Try to activate the project venv if it exists
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

:: Start the FastAPI server
python -m uvicorn server.api:app --host 0.0.0.0 --port 8000

pause
