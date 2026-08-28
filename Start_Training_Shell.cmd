@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
call "%ROOT%\config\portable_env.cmd"
set "MPPS_PORTABLE_ROOT=%ROOT%"
set "PYTHONPATH=%ROOT%"
set "PATH=%ROOT%\runtime\postgresql\bin;%ROOT%\runtime\python;%PATH%"
call "%ROOT%\Start_Database_Only.cmd"
if errorlevel 1 exit /b 1
cd /d "%ROOT%"
echo MPPS portable training shell
echo Python: "%ROOT%\runtime\python\python.exe"
echo Root:   "%ROOT%"
cmd /k
