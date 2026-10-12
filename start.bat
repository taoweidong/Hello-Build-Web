@echo off
rem One-click launcher for Build Strategy Config System (frontend + backend dev servers).
rem All arguments are passed through to start.ps1, e.g.:
rem   start.bat              start both services and open the browser
rem   start.bat -Stop        stop both services
rem   start.bat -Status      show service status
rem   start.bat -Restart     restart both services
rem   start.bat -NoBrowser   start without opening the browser
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if errorlevel 1 (
    echo.
    echo [start.bat] Failed - see the messages above. Press any key to exit...
    pause >nul
)
