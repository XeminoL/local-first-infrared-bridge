param(
    [Parameter(Mandatory = $true)]
    [string]$Esp32Address
)

$ErrorActionPreference = "Continue"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Results = Join-Path $Here "results"
New-Item -ItemType Directory -Force $Results | Out-Null
$Log = Join-Path $Results "$(Get-Date -Format 'yyyyMMdd-HHmmss')-offline-log.txt"
$InternetHosts = @("1.1.1.1", "8.8.8.8")
$InternetUrl = "https://www.google.com"

function Write-Log([string]$Message) {
    $Message | Tee-Object -FilePath $Log -Append
}

function Test-Internet {
    foreach ($address in $InternetHosts) {
        if (Test-Connection -ComputerName $address -Count 2 -Quiet) { return $true }
    }
    try {
        Invoke-WebRequest -Uri $InternetUrl -UseBasicParsing -TimeoutSec 5 | Out-Null
        return $true
    } catch { return $false }
}

Set-Location $Here

Write-Log "== check before: internet must be unreachable"
if (Test-Internet) {
    Write-Log "ABORT: internet is still reachable. Turn off mobile data and run again."
    exit 1
}
Write-Log "internet unreachable at $(Get-Date -Format 'HH:mm:ss')"
Write-Log "esp32 reachable: $(Test-Connection -ComputerName $Esp32Address -Count 2 -Quiet)"

Write-Log "== loopback (NEC button, 100 presses)"
python loopback.py --trials 100 --label offline-loopback 2>&1 | Tee-Object -FilePath $Log -Append

Write-Log "== climate sweep (Daikin, 1 round)"
python climate_sweep.py --rounds 1 --label offline-climate 2>&1 | Tee-Object -FilePath $Log -Append

Write-Log "== check after: internet must still be unreachable"
Write-Log "internet reachable after: $(Test-Internet) at $(Get-Date -Format 'HH:mm:ss')"
Write-Log "DONE. Turn mobile data back on."
