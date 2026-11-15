param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [switch]$EnableStartupFullRefresh = $true,
    [int]$StartupTimeoutSeconds = 45
)

$ErrorActionPreference = "Stop"

function Write-Pass([string]$Message) {
    Write-Host "[PASS] $Message" -ForegroundColor Green
}

function Write-Fail([string]$Message) {
    Write-Host "[FAIL] $Message" -ForegroundColor Red
}

function Load-EnvFile([string]$Path) {
    if (-not (Test-Path $Path)) {
        return
    }

    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line) { return }
        if ($line.StartsWith("#")) { return }

        $parts = $line -split "=", 2
        if ($parts.Count -eq 2) {
            $name = $parts[0].Trim()
            $value = $parts[1].Trim()
            Set-Item -Path ("Env:" + $name) -Value $value
        }
    }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

Load-EnvFile -Path (Join-Path $repoRoot ".env")

if ($EnableStartupFullRefresh) {
    $env:STARTUP_FULL_REFRESH = "true"
}

$pythonExe = Join-Path $repoRoot ".venv/Scripts/python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

$backendPath = Join-Path $repoRoot "backend"
$logDir = Join-Path $backendPath "data"
New-Item -Path $logDir -ItemType Directory -Force | Out-Null
$outLog = Join-Path $logDir "smoke-uvicorn.out.log"
$errLog = Join-Path $logDir "smoke-uvicorn.err.log"

$process = $null

try {
    $startProcessArgs = @{
        FilePath = $pythonExe
        ArgumentList = @(
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000"
        )
        WorkingDirectory = $backendPath
        PassThru = $true
        RedirectStandardOutput = $outLog
        RedirectStandardError = $errLog
    }
    $process = Start-Process @startProcessArgs

    $startupDeadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
    $isHealthy = $false

    while ((Get-Date) -lt $startupDeadline) {
        try {
            $health = Invoke-RestMethod -Uri "$BaseUrl/api/health" -Method Get -TimeoutSec 3
            if ($health.status -eq "ok") {
                $isHealthy = $true
                break
            }
        }
        catch {
            if ($process.HasExited) {
                throw "Uvicorn exited before health check succeeded."
            }
        }
    }

    if (-not $isHealthy) {
        throw "Timed out waiting for /api/health."
    }

    Write-Pass "Health endpoint is reachable."

    $queue = Invoke-RestMethod -Uri "$BaseUrl/api/debug/queue-status" -Method Get -TimeoutSec 10
    $cacheAge = Invoke-RestMethod -Uri "$BaseUrl/api/debug/cache-age" -Method Get -TimeoutSec 10

    $datasetNames = @($cacheAge.datasets.PSObject.Properties.Name)
    $expectedDatasets = @(
        "org",
        "repos",
        "raw_repos",
        "contributors",
        "activity",
        "commit_activity"
    )
    $missingDatasets = @($expectedDatasets | Where-Object { $_ -notin $datasetNames })

    if ($missingDatasets.Count -gt 0) {
        throw "Missing datasets from /api/debug/cache-age: $($missingDatasets -join ', ')"
    }

    Write-Pass "Cache-age endpoint reports all expected datasets."

    if ($EnableStartupFullRefresh) {
        $jobNames = @($queue.api_queue.jobs.PSObject.Properties.Name)
        $org = $queue.github_org
        $expectedJobs = @(
            "org:$org",
            "repos:$org",
            "activity:$org",
            "contributors:$org",
            "commit_activity:$org"
        )
        $missingJobs = @($expectedJobs | Where-Object { $_ -notin $jobNames })

        if ($missingJobs.Count -gt 0) {
            throw "Missing startup refresh jobs: $($missingJobs -join ', ')"
        }

        Write-Pass "Startup full-refresh jobs are present in queue status."
    }

    Write-Host ("[INFO] queue_size={0}, running={1}" -f $queue.api_queue.queue_size, @($queue.api_queue.running_keys).Count)
    Write-Pass "Smoke test completed successfully."
    exit 0
}
catch {
    Write-Fail $_.Exception.Message
    if (Test-Path $errLog) {
        Write-Host "[INFO] Last stderr lines:" -ForegroundColor Yellow
        Get-Content $errLog -Tail 40
    }
    exit 1
}
finally {
    if ($process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
    }
}
