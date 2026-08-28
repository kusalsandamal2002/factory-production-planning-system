@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
call "%ROOT%\config\portable_env.cmd"
set "MPPS_PORTABLE_ROOT=%ROOT%"
set "PYTHONPATH=%ROOT%"

"%ROOT%\runtime\python\python.exe" "%ROOT%\tools\portable_db_control.py" start
exit /b %errorlevel%
