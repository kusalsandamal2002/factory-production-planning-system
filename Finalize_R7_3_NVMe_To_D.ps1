$ErrorActionPreference = 'Stop'
$Root = 'D:\Pa App'
$Nvme = 'C:\MPPS_ML_FAST'
$Cpg = Join-Path $Nvme 'pgdata'
$Dpg = Join-Path $Root 'portable_db\pgdata'
$CInbox = Join-Path $Nvme 'historical_inbox'
$DInbox = Join-Path $Root 'ml_workspace\historical_inbox'
$DArchive = Join-Path $Root 'ml_workspace\historical_inbox_D_HARDLINKS_BACKUP_R72'
$Active = Join-Path $Nvme 'R73_ACTIVE.flag'
$Pause = Join-Path $Nvme 'PAUSE_REQUESTED.flag'
$Complete = Join-Path $Nvme 'R73_PIPELINE_COMPLETE.flag'
$DbCtl = Join-Path $Root 'R7_3_DB_Control.cmd'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$DbBackupRoot = Join-Path $Root 'backups\database'
$ModelsBackupRoot = Join-Path $Root 'backups\releases'
$DModels = Join-Path $Root 'models'
$CModels = Join-Path $Nvme 'models'
$DReports = Join-Path $Root 'reports'
$CReports = Join-Path $Nvme 'reports'

function Get-TreeStats([string]$Path) {
    $items = @(Get-ChildItem -LiteralPath $Path -File -Recurse -Force -ErrorAction Stop)
    $bytes = ($items | Measure-Object -Property Length -Sum).Sum
    if ($null -eq $bytes) { $bytes = 0 }
    [PSCustomObject]@{ Count = $items.Count; Bytes = [int64]$bytes }
}
function Invoke-Robo([string]$Source, [string]$Dest) {
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    & robocopy.exe $Source $Dest /MIR /COPY:DAT /DCOPY:DAT /R:1 /W:1 /MT:8 /XJ
    $rc = $LASTEXITCODE
    if ($rc -ge 8) { throw "Robocopy failed with exit code $rc" }
}
function Remove-JunctionIfPresent([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $item = Get-Item -LiteralPath $Path -Force
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) {
        throw "Expected junction but found a normal directory: $Path"
    }
    & cmd.exe /c "rmdir `"$Path`""
    if ($LASTEXITCODE -ne 0) { throw "Could not remove junction: $Path" }
}
function New-Junction([string]$Link, [string]$Target) {
    & cmd.exe /c "mklink /J `"$Link`" `"$Target`""
    if ($LASTEXITCODE -ne 0) { throw "Could not create junction: $Link -> $Target" }
}

$training = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -eq 'python.exe' -and $_.CommandLine -like '*run_ml_finalization.py*' -and $_.CommandLine -like '*D:\Pa App*'
})
if ($training.Count -gt 0) { throw 'Training is still running. Use Pause_And_Stop_R7_3_ML.cmd first.' }
if (-not (Test-Path -LiteralPath (Join-Path $Cpg 'PG_VERSION'))) { throw "C: PostgreSQL cluster missing: $Cpg" }
if (-not (Test-Path -LiteralPath $DArchive)) { throw "D: historical authority missing: $DArchive" }
if (-not (Test-Path -LiteralPath $Complete)) { throw 'Final ML pipeline completion marker is missing. Resume training; do not finalize a paused/partial run.' }

$remaining = 0
if (Test-Path -LiteralPath $CInbox) {
    $remaining = @(Get-ChildItem -LiteralPath $CInbox -File -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in '.xlsx','.xlsm' }).Count
}
if ($remaining -gt 0) {
    throw "Historical ingestion is not complete. $remaining workbook cache files remain on C:. Resume training first."
}

Write-Host 'Stopping C: PostgreSQL...'
& $DbCtl stop C
if ($LASTEXITCODE -ne 0) { throw 'Could not stop C: PostgreSQL cleanly.' }

New-Item -ItemType Directory -Force -Path $DbBackupRoot,$ModelsBackupRoot,$DReports | Out-Null
$OldDbBackup = Join-Path $DbBackupRoot ("pgdata_PRE_R73_FINAL_" + $Stamp)
$OldModelsBackup = Join-Path $ModelsBackupRoot ("models_PRE_R73_FINAL_" + $Stamp)
$databaseMoved = $false
$modelsMoved = $false

try {
    if (Test-Path -LiteralPath $Dpg) {
        Move-Item -LiteralPath $Dpg -Destination $OldDbBackup
        $databaseMoved = $true
    }
    Write-Host 'Copying final NVMe PostgreSQL cluster to D:...'
    Invoke-Robo $Cpg $Dpg
    $src = Get-TreeStats $Cpg
    $dst = Get-TreeStats $Dpg
    if ($src.Count -ne $dst.Count -or $src.Bytes -ne $dst.Bytes) {
        throw "Final DB verification failed. C=$($src.Count)/$($src.Bytes), D=$($dst.Count)/$($dst.Bytes)"
    }

    if (Test-Path -LiteralPath $DModels) {
        Move-Item -LiteralPath $DModels -Destination $OldModelsBackup
        $modelsMoved = $true
    }
    if (Test-Path -LiteralPath $CModels) {
        Invoke-Robo $CModels $DModels
    } else {
        New-Item -ItemType Directory -Force -Path $DModels | Out-Null
    }
    if (Test-Path -LiteralPath $CReports) {
        & robocopy.exe $CReports $DReports /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /MT:4 /XJ
        if ($LASTEXITCODE -ge 8) { throw "Report sync failed with exit code $LASTEXITCODE" }
    }

    Remove-JunctionIfPresent $DInbox
    New-Junction $DInbox $DArchive
    Remove-Item -LiteralPath $Active -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $Pause -Force -ErrorAction SilentlyContinue

    Write-Host 'Starting verified D: PostgreSQL...'
    & $DbCtl start D
    if ($LASTEXITCODE -ne 0) { throw 'Final D: PostgreSQL did not become read-write ready.' }

    Write-Host 'D: database verification succeeded. Cleaning C: training workspace...'
    foreach ($p in @($Cpg,$CInbox,$CModels,$CReports,(Join-Path $Nvme 'logs'),(Join-Path $Nvme 'ml_workspace'))) {
        if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction Stop }
    }
    foreach ($p in @((Join-Path $Nvme 'R73_resume_state.json'),$Active,$Pause,$Complete)) {
        Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Directory -Force -Path $Nvme | Out-Null
    Set-Content -LiteralPath (Join-Path $Nvme 'R73_FINALIZED.txt') -Value ("Finalized to D: at " + (Get-Date).ToString('s')) -Encoding ASCII

    Write-Host ''
    Write-Host '=== R7.3 FINAL SYNC SUCCESS ===' -ForegroundColor Green
    Write-Host "Final PostgreSQL: $Dpg"
    Write-Host "Final models    : $DModels"
    Write-Host "Reports         : $DReports"
    Write-Host "Pre-final DB backup retained: $OldDbBackup"
    if ($modelsMoved) { Write-Host "Pre-final model backup retained: $OldModelsBackup" }
    Write-Host 'C: NVMe training data has been released after D: verification.'
}
catch {
    Write-Host "FINALIZE ERROR: $($_.Exception.Message)" -ForegroundColor Red
    try { & $DbCtl stop D | Out-Null } catch {}
    try {
        if (Test-Path -LiteralPath $Dpg) { Remove-Item -LiteralPath $Dpg -Recurse -Force }
        if ($databaseMoved -and (Test-Path -LiteralPath $OldDbBackup)) { Move-Item -LiteralPath $OldDbBackup -Destination $Dpg }
        if ($modelsMoved) {
            if (Test-Path -LiteralPath $DModels) { Remove-Item -LiteralPath $DModels -Recurse -Force }
            if (Test-Path -LiteralPath $OldModelsBackup) { Move-Item -LiteralPath $OldModelsBackup -Destination $DModels }
        }
        Set-Content -LiteralPath $Active -Value 'R7.3 Full-Speed NVMe mode active' -Encoding ASCII
        Remove-JunctionIfPresent $DInbox
        if (Test-Path -LiteralPath $CInbox) { New-Junction $DInbox $CInbox }
        & $DbCtl start C | Out-Null
    } catch {}
    throw
}