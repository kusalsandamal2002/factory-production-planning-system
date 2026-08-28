@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
call "%ROOT%\config\portable_env.cmd"
set "MPPS_PORTABLE_ROOT=%ROOT%"
set "PYTHONPATH=%ROOT%"

echo Stopping MPPS portable PostgreSQL safely...
"%ROOT%\runtime\python\python.exe" "%ROOT%\tools\portable_db_control.py" stop
if errorlevel 1 (
    echo ERROR: PostgreSQL did not stop cleanly. Do NOT disconnect the drive yet.
    exit /b 1
)

echo.
echo MPPS database is stopped.
echo Close any remaining files/windows using this drive, then use Windows "Safely Remove Hardware".
exit /b 0
