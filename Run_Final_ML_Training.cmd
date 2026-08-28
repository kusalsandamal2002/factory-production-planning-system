@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "NVME=C:\MPPS_ML_FAST"
set "MPPS_PORTABLE_ROOT=%ROOT%"

if not exist "%ROOT%\runtime\python\python.exe" (
  echo ERROR: Portable Python runtime not found.
  exit /b 1
)
if not exist "%ROOT%\config\portable_env.cmd" (
  echo ERROR: Portable database environment file not found.
  exit /b 1
)
if not exist "%NVME%\pgdata\PG_VERSION" (
  echo ERROR: R7.3 NVMe PostgreSQL cluster not found at %NVME%\pgdata
  echo Run the R7.3 Full-Speed NVMe updater first.
  exit /b 1
)
if not exist "%NVME%\historical_inbox" (
  echo ERROR: R7.3 NVMe Historical Inbox is missing.
  exit /b 1
)

call "%ROOT%\config\portable_env.cmd"
set "MPPS_PORTABLE_ROOT=%ROOT%"
set "MPPS_NVME_ROOT=%NVME%"
set "MPPS_R73_ACTIVE_FLAG=%NVME%\R73_ACTIVE.flag"
set "MPPS_PGDATA=%NVME%\pgdata"
set "MPPS_PGLOGS=%NVME%\logs"
set "MPPS_ML_WORKSPACE=%NVME%\ml_workspace"
set "MPPS_HISTORICAL_INBOX=%NVME%\historical_inbox"
set "MPPS_HISTORICAL_ARCHIVE_ROOT=%ROOT%\ml_workspace\historical_inbox_D_HARDLINKS_BACKUP_R72"
set "MPPS_MODELS_DIR=%NVME%\models"
set "MPPS_REPORTS_DIR=%NVME%\reports"
set "MPPS_ML_PAUSE_FLAG=%NVME%\PAUSE_REQUESTED.flag"
set "MPPS_ML_RESUME_STATE=%NVME%\R73_resume_state.json"
set "MPPS_NVME_ROLLING_DELETE=1"
set "MPPS_NVME_MIN_FREE_GB=20"
set "MPPS_R74_INGEST_WORKERS=2"
set "MPPS_R741_BULK_HISTORY=1"
set "MPPS_R742_DEFER_AI_GLOBAL=1"
set "MPPS_R743_MAX_THROUGHPUT=1"
set "TEMP=%NVME%\temp"
set "TMP=%NVME%\temp"
set "JOBLIB_TEMP_FOLDER=%NVME%\temp\joblib"
if not exist "%NVME%\temp" mkdir "%NVME%\temp" >nul 2>&1
if not exist "%JOBLIB_TEMP_FOLDER%" mkdir "%JOBLIB_TEMP_FOLDER%" >nul 2>&1

if exist "%MPPS_ML_PAUSE_FLAG%" del /q "%MPPS_ML_PAUSE_FLAG%" >nul 2>&1
if exist "%NVME%\R73_PIPELINE_COMPLETE.flag" del /q "%NVME%\R73_PIPELINE_COMPLETE.flag" >nul 2>&1
> "%MPPS_R73_ACTIVE_FLAG%" echo R7.3 Full-Speed NVMe mode active

set /a MPPS_ML_THREADS=%NUMBER_OF_PROCESSORS%-1
if %MPPS_ML_THREADS% LSS 1 set "MPPS_ML_THREADS=1"
set "MPPS_ML_PROFILE=MAX_QUALITY"
set "OMP_NUM_THREADS=%MPPS_ML_THREADS%"
set "MKL_NUM_THREADS=%MPPS_ML_THREADS%"
set "OPENBLAS_NUM_THREADS=%MPPS_ML_THREADS%"
set "NUMEXPR_NUM_THREADS=%MPPS_ML_THREADS%"
set "OMP_DYNAMIC=FALSE"
set "CUDA_DEVICE_ORDER=PCI_BUS_ID"
set "CUDA_VISIBLE_DEVICES=0"

"%ROOT%\runtime\python\python.exe" "%ROOT%\tools\training_db_guard.py"
if errorlevel 1 (
  echo ERROR: R7.3 NVMe PostgreSQL is not read-write ready.
  exit /b 1
)

echo.
echo ============================================================
echo  MPPS R7.4.3 MAX-THROUGHPUT NVMe + CUDA ML TRAINING
echo ============================================================
echo Excel cache : %MPPS_HISTORICAL_INBOX%
echo PostgreSQL  : %MPPS_PGDATA%
echo Models      : %MPPS_MODELS_DIR%
echo Reports     : %MPPS_REPORTS_DIR%
echo D: source   : preserved / read-only archive authority
echo Rolling mode: committed/duplicate C: cache files are deleted
echo Ingest CPU  : %MPPS_R74_INGEST_WORKERS% parallel XLSX analyzers; DB commits serialized
echo DB Turbo    : R7.4.3 indexed identity cache + single-pass identity + batch learning/AI truth
echo Safe pause  : use Pause_And_Stop_R7_3_ML.cmd
echo.

"%ROOT%\runtime\python\python.exe" "%ROOT%\tools\run_ml_finalization.py" --all --install-runtime
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
  echo SUCCESS: R7.3 Full-Speed ML training pipeline completed.
) else if "%RC%"=="3" (
  echo R7.3 ingestion completed, but some models still lack trustworthy data/labels.
) else if "%RC%"=="4" (
  echo PAUSED SAFELY: resume later with this same launcher.
  exit /b %RC%
) else if "%RC%"=="5" (
  echo PAUSED FOR LOW C: SPACE: free space before resuming.
  exit /b %RC%
) else (
  echo R7.3 pipeline ended with warnings/errors. Review the newest C: report.
)

echo.
pause
exit /b %RC%
