@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

if not exist "%ROOT%\config\portable_env.cmd" (
    echo ERROR: config\portable_env.cmd is missing.
    pause
    exit /b 2
)

call "%ROOT%\config\portable_env.cmd"
if errorlevel 1 exit /b 2

set "PYTHONPATH=%ROOT%"
set "MPPS_PORTABLE_ROOT=%ROOT%"
set "MPPS_PGDATA=%ROOT%\portable_db\pgdata"
set "MPPS_PGLOGS=%ROOT%\logs"
set "MPPS_MODELS_DIR=%ROOT%\models"
set "MPPS_REPORTS_DIR=%ROOT%\reports"

cd /d "%ROOT%"
call "%ROOT%\R7_3_DB_Control.cmd" start D
if errorlevel 1 (
    echo ERROR: Permanent D: PostgreSQL did not become read-write ready.
    pause
    exit /b 3
)

"%ROOT%\runtime\python\python.exe" -m app.main
exit /b %ERRORLEVEL%
