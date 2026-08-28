@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Finalize_R7_3_NVMe_To_D.ps1"
echo.
pause
exit /b %ERRORLEVEL%