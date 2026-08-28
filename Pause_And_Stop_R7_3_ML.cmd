@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Pause_And_Stop_R7_3_ML.ps1"
echo.
pause
exit /b %ERRORLEVEL%