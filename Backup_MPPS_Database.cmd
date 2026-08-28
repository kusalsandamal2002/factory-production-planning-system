@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
call "%ROOT%\config\portable_env.cmd"
call "%ROOT%\Start_Database_Only.cmd"
if errorlevel 1 exit /b 1

set "STAMP=%date:~-4%%date:~4,2%%date:~7,2%_%time:~0,2%%time:~3,2%%time:~6,2%"
set "STAMP=%STAMP: =0%"
set "OUT=%ROOT%\backups\database\MPPS_PORTABLE_%STAMP%.dump"

set "PGPASSWORD=%MPPS_DB_PASSWORD%"
"%ROOT%\runtime\postgresql\bin\pg_dump.exe" ^
  --host=127.0.0.1 ^
  --port=%MPPS_DB_PORT% ^
  --username=%MPPS_DB_USER% ^
  --format=custom ^
  --no-owner ^
  --no-privileges ^
  --file="%OUT%" ^
  %MPPS_DB_NAME%

if errorlevel 1 (
    echo ERROR: Database backup failed.
    exit /b 1
)

echo Backup created:
echo %OUT%
exit /b 0
