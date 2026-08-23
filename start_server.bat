@echo off
title PET NEXA - Development & Prototype Server
chcp 65001 >nul
cls

echo ================================================================
echo           🐾 PET NEXA - PROTOTYPE & DEVELOPMENT SERVER
echo ================================================================
echo.

:: Detect local IPv4 address dynamically using Python
for /f "delims=" %%I in ('python -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); (s.connect(('8.8.8.8', 80)) if True else None); print(s.getsockname()[0]); s.close()" 2^>nul') do set "LOCAL_IP=%%I"

if "%LOCAL_IP%"=="" (
    for /f "tokens=2 delims=:" %%A in ('ipconfig ^| findstr /c:"IPv4 Address" 2^>nul') do (
        if not defined LOCAL_IP (
            for /f "tokens=1" %%B in ("%%A") do set "LOCAL_IP=%%B"
        )
    )
)

if "%LOCAL_IP%"=="" set "LOCAL_IP=127.0.0.1"

echo  [✓] Server is starting on port 5000 (accessible on LAN)
echo.
echo  • Local Laptop URL:   http://127.0.0.1:5000
echo  • Localhost URL:      http://localhost:5000
echo  • Mobile / LAN URL:   http://%LOCAL_IP%:5000
echo.
echo ================================================================
echo  * Connect your mobile device to the same Wi-Fi network.
echo  * Open http://%LOCAL_IP%:5000 in your phone's browser.
echo ================================================================
echo.
echo Starting Flask application...
echo.

cd /d "%~dp0backend"

:: Activate virtualenv if present
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else if exist "..\venv\Scripts\activate.bat" (
    call ..\venv\Scripts\activate.bat
)

python app.py

pause
