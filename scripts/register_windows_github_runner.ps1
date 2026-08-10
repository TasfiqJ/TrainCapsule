param(
    [string]$Distribution = "Ubuntu-22.04",
    [string]$TaskName = "TrainCapsule GitHub Runner",
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"
$Wsl = Join-Path $env:SystemRoot "System32\wsl.exe"
if (-not (Test-Path $Wsl)) {
    throw "wsl.exe was not found. Install WSL2 first."
}

$LinuxHome = (& $Wsl -d $Distribution -- bash -lc 'printf "%s" "$HOME"').Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($LinuxHome)) {
    throw "Could not resolve the Linux home directory in $Distribution."
}
$RunnerScript = "$LinuxHome/.local/share/traincapsule-actions-runner/run-traincapsule-runner-foreground.sh"
& $Wsl -d $Distribution -- test -x $RunnerScript
if ($LASTEXITCODE -ne 0) {
    throw "The private TrainCapsule GitHub runner entrypoint was not found."
}

$Arguments = "-d `"$Distribution`" -- bash `"$RunnerScript`""
$Action = New-ScheduledTaskAction -Execute $Wsl -Argument $Arguments
$WindowsIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$LogonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $WindowsIdentity
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

$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $ExistingTask) {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Triggers `
        -Principal $Principal `
        -Settings $Settings `
        -Description "Runs the private TrainCapsule self-hosted GitHub Actions runner in WSL without hosted-runner billing." | Out-Null
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
if ($StartNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Started scheduled task."
}
