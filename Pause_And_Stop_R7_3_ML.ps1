$ErrorActionPreference = 'Stop'
$Root = 'D:\Pa App'
$Nvme = 'C:\MPPS_ML_FAST'
$Pause = Join-Path $Nvme 'PAUSE_REQUESTED.flag'
$DbCtl = Join-Path $Root 'R7_3_DB_Control.cmd'

if (-not (Test-Path -LiteralPath $Nvme)) {
    throw "R7.3 NVMe workspace not found: $Nvme"
}
New-Item -ItemType Directory -Force -Path $Nvme | Out-Null
Set-Content -LiteralPath $Pause -Value ("Safe pause requested at " + (Get-Date).ToString('s')) -Encoding ASCII
Write-Host 'Safe pause requested. Waiting for the current workbook/model boundary...'

$deadline = (Get-Date).AddHours(2)
while ($true) {
    $running = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -eq 'python.exe' -and
        $_.CommandLine -like '*run_ml_finalization.py*' -and
        $_.CommandLine -like '*D:\Pa App*'
    })
    if ($running.Count -eq 0) { break }
    if ((Get-Date) -ge $deadline) {
        Write-Host 'ERROR: Training did not reach a safe boundary within 2 hours.' -ForegroundColor Red
        Write-Host 'Do NOT disconnect D:. Use Ctrl+C once in the training window, wait for it to exit, then run this stop launcher again.'
        exit 2
    }
    Start-Sleep -Seconds 3
}

& $DbCtl stop C
if ($LASTEXITCODE -ne 0) {
    Write-Host 'ERROR: NVMe PostgreSQL did not stop cleanly. Do NOT disconnect D:.' -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host ''
Write-Host 'SAFE STOP COMPLETE.' -ForegroundColor Green
Write-Host 'Training is stopped at a safe boundary and C: PostgreSQL is stopped.'
Write-Host 'You can now close MPPS terminals and safely eject/disconnect D:.'
Write-Host 'At home/office reconnect D: and run D:\Pa App\Run_Final_ML_Training.cmd to resume.'