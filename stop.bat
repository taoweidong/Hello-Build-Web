@echo off
rem Stop frontend + backend dev services (equivalent to: .\start.ps1 -Stop)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" -Stop
echo.
echo [stop.bat] Done. Press any key to exit...
pause >nul
