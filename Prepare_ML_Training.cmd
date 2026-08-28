@echo off
setlocal
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "MPPS_PORTABLE_ROOT=%ROOT%"

"%ROOT%\runtime\python\python.exe" "%ROOT%\tools\portable_db_control.py" start
if errorlevel 1 exit /b 1

"%ROOT%\runtime\python\python.exe" "%ROOT%\tools\run_ml_finalization.py" --prepare
set "RC=%ERRORLEVEL%"
pause
exit /b %RC%
