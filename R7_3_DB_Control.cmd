@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "NVME=C:\MPPS_ML_FAST"
if not exist "%ROOT%\config\portable_env.cmd" exit /b 2
call "%ROOT%\config\portable_env.cmd"
set "MPPS_PORTABLE_ROOT=%ROOT%"
set "MPPS_NVME_ROOT=%NVME%"
set "MPPS_R73_ACTIVE_FLAG=%NVME%\R73_ACTIVE.flag"
if /I "%~2"=="C" (
  set "MPPS_PGDATA=%NVME%\pgdata"
  set "MPPS_PGLOGS=%NVME%\logs"
) else if /I "%~2"=="D" (
  set "MPPS_PGDATA=%ROOT%\portable_db\pgdata"
  set "MPPS_PGLOGS=%ROOT%\logs"
) else (
  echo Usage: R7_3_DB_Control.cmd start^|stop^|status C^|D
  exit /b 2
)
"%ROOT%\runtime\python\python.exe" "%ROOT%\tools\portable_db_control.py" %~1
exit /b %ERRORLEVEL%