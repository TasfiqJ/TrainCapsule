[CmdletBinding()]
param(
    [ValidateSet(
        "Status", "Overview", "Start", "Pause", "Resume", "Recover", "Stop",
        "ScheduleDryRun", "MilestoneStatus", "Verify", "Logs", "Queue", "GitHub"
    )]
    [string]$Action = "Status",
    [string]$RepoPath = $env:TCF_REPO_PATH,
    [string]$WslDistribution = $env:TCF_WSL_DISTRIBUTION,
    [string]$FactoryRuntimePath = "scripts/factory_control.sh"
)

$ErrorActionPreference = "Stop"
$Wsl = Join-Path $env:SystemRoot "System32\wsl.exe"
if (-not (Test-Path $Wsl)) {
    throw "wsl.exe was not found. Install WSL2 first."
}

# When launched from a \\wsl.localhost share, derive both values from the script location.
# Otherwise require -RepoPath (or TCF_REPO_PATH); no user/distribution path is assumed.
if ([string]::IsNullOrWhiteSpace($RepoPath) -and
    $PSScriptRoot -match '^\\\\wsl(?:\.localhost)?\\([^\\]+)\\(.+)$') {
    if ([string]::IsNullOrWhiteSpace($WslDistribution)) {
        $WslDistribution = $Matches[1]
    }
    $RepoPath = "/" + $Matches[2].Replace("\", "/")
}
if ([string]::IsNullOrWhiteSpace($RepoPath)) {
    throw "Specify -RepoPath or set TCF_REPO_PATH."
}
foreach ($Value in @($RepoPath, $WslDistribution, $FactoryRuntimePath)) {
    if ($Value -match "[`r`n`0]") {
        throw "Control parameters may not contain control characters."
    }
}

if ($FactoryRuntimePath.StartsWith("/")) {
    $Runtime = $FactoryRuntimePath
}
else {
    $Runtime = $RepoPath.TrimEnd("/") + "/" + $FactoryRuntimePath.TrimStart("/")
}

function Invoke-TrainCapsuleWsl {
    param([string[]]$LinuxArguments)
    $WslArguments = @()
    if (-not [string]::IsNullOrWhiteSpace($WslDistribution)) {
        $WslArguments += @("-d", $WslDistribution)
    }
    $WslArguments += "--"
    $WslArguments += $LinuxArguments
    & $Wsl @WslArguments
    if ($LASTEXITCODE -ne 0) {
        throw "TrainCapsule control action failed with exit code $LASTEXITCODE."
    }
}

Invoke-TrainCapsuleWsl -LinuxArguments @("test", "-x", $Runtime)

$ControlAction = switch ($Action) {
    "Status" { "status" }
    "Overview" { "status" }
    "Start" { "start" }
    "Pause" { "pause" }
    "Resume" { "resume" }
    "Recover" { "recover" }
    "Stop" { "stop" }
    "ScheduleDryRun" { "schedule-dry-run" }
    "MilestoneStatus" { "milestone-status" }
    "Verify" { "verify" }
    "Logs" { "logs" }
    "Queue" { "queue" }
    "GitHub" { "github" }
}

# The runtime script owns environment loading and redaction. OAuth values are never requested,
# interpolated, printed, or passed as command-line arguments by this Windows control surface.
Invoke-TrainCapsuleWsl -LinuxArguments @("bash", $Runtime, $ControlAction)
