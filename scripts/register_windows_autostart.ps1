param(
    [string]$Distribution = "Ubuntu",
    [string]$LinuxRepoPath = "",
    [string]$TaskName = "TrainCapsule Lights-Out Autopilot",
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"
$Wsl = Join-Path $env:SystemRoot "System32\wsl.exe"
if (-not (Test-Path $Wsl)) {
    throw "wsl.exe was not found. Install WSL2 first."
}

# Resolve the Linux home through the selected distribution. This avoids a literal '~'
# inside bash quotes, which would not expand under Task Scheduler.
if ([string]::IsNullOrWhiteSpace($LinuxRepoPath)) {
    $LinuxHome = (& $Wsl -d $Distribution -- bash -lc 'printf "%s" "$HOME"').Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($LinuxHome)) {
        throw "Could not resolve the Linux home directory in $Distribution."
    }
    $LinuxRepoPath = "$LinuxHome/projects/traincapsule"
}

if ($LinuxRepoPath.Contains("'")) {
    throw "LinuxRepoPath may not contain an apostrophe because it is passed through bash -lc."
}
$RepoQuoted = "'$LinuxRepoPath'"
$EntryQuoted = "'$LinuxRepoPath/scripts/windows_task_entrypoint.sh'"

# Validate the selected distribution, repository, and executable entrypoint before registration.
& $Wsl -d $Distribution -- bash -lc "test -x $EntryQuoted"
if ($LASTEXITCODE -ne 0) {
    throw "The Linux repository or executable entrypoint was not found at $LinuxRepoPath in $Distribution."
}

$LinuxCommand = "cd $RepoQuoted && exec ./scripts/windows_task_entrypoint.sh"
$Arguments = "-d `"$Distribution`" -- bash -lc `"$LinuxCommand`""
$Action = New-ScheduledTaskAction -Execute $Wsl -Argument $Arguments

$WindowsIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
if ([string]::IsNullOrWhiteSpace($WindowsIdentity)) {
    throw "Could not resolve the current Windows identity for Task Scheduler."
}

# Trigger 1 starts the factory immediately after the operator logs in.
$LogonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $WindowsIdentity

# Trigger 2 is a recovery heartbeat. If WSL, Windows, or the factory process stopped,
# Task Scheduler attempts to start it every 15 minutes. MultipleInstances IgnoreNew
# prevents a second instance while the foreground autopilot is already alive.
$RecoveryTrigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$Triggers = @($LogonTrigger, $RecoveryTrigger)

$Principal = New-ScheduledTaskPrincipal `
    -UserId $WindowsIdentity `
    -LogonType Interactive `
    -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew

$Description = "Runs the TrainCapsule autonomous Claude Max product factory in a foreground WSL process after logon, with a 15-minute recovery trigger."
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $ExistingTask) {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Triggers `
        -Principal $Principal `
        -Settings $Settings `
        -Description $Description | Out-Null
}
else {
    Set-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Triggers `
        -Principal $Principal `
        -Settings $Settings | Out-Null
}

Write-Host "Registered Windows scheduled task: $TaskName"
Write-Host "Distribution: $Distribution"
Write-Host "Linux repository: $LinuxRepoPath"
Write-Host "Triggers: at logon plus a 15-minute recovery heartbeat."
Write-Host "The foreground WSL process stays alive while the autopilot is running or waiting for a quota reset."
Write-Host "Logs: $LinuxRepoPath/factory/logs/autopilot.log"

if ($StartNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Started scheduled task."
}
