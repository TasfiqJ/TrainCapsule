param(
    [string]$RepoPath = $env:TCF_REPO_PATH,
    [string]$WslDistribution = $env:TCF_WSL_DISTRIBUTION,
    [string]$FactoryRuntimePath = "scripts/windows_task_entrypoint.sh",
    [string]$TaskName = "TrainCapsule Lights-Out Autopilot",
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"
$Wsl = Join-Path $env:SystemRoot "System32\wsl.exe"
if (-not (Test-Path $Wsl)) {
    throw "wsl.exe was not found. Install WSL2 first."
}
if ([string]::IsNullOrWhiteSpace($RepoPath)) {
    throw "Specify -RepoPath or set TCF_REPO_PATH."
}
foreach ($Value in @($RepoPath, $WslDistribution, $FactoryRuntimePath, $TaskName)) {
    if ($Value -match "[`r`n`0]") {
        throw "Registration parameters may not contain control characters."
    }
}
if ($FactoryRuntimePath.StartsWith("/")) {
    $Runtime = $FactoryRuntimePath
}
else {
    $Runtime = $RepoPath.TrimEnd("/") + "/" + $FactoryRuntimePath.TrimStart("/")
}
if ($RepoPath.Contains("'") -or $Runtime.Contains("'")) {
    throw "RepoPath and FactoryRuntimePath may not contain apostrophes."
}

$ValidationArguments = @()
if (-not [string]::IsNullOrWhiteSpace($WslDistribution)) {
    $ValidationArguments += @("-d", $WslDistribution)
}
$ValidationArguments += @("--", "test", "-x", $Runtime)
& $Wsl @ValidationArguments
if ($LASTEXITCODE -ne 0) {
    throw "The executable factory runtime was not found at $Runtime."
}

$LinuxCommand = "cd '$RepoPath' && exec '$Runtime'"
$DistributionArguments = ""
if (-not [string]::IsNullOrWhiteSpace($WslDistribution)) {
    $DistributionArguments = "-d `"$WslDistribution`" "
}
$Arguments = "$DistributionArguments-- bash -lc `"$LinuxCommand`""
$EscapedArguments = $Arguments.Replace("'", "''")
$LauncherSource = @"
`$Wsl = Join-Path `$env:SystemRoot 'System32\wsl.exe'
`$WslArguments = '$EscapedArguments'
Start-Process -FilePath `$Wsl -ArgumentList `$WslArguments -WindowStyle Hidden
"@
$EncodedLauncher = [Convert]::ToBase64String(
    [Text.Encoding]::Unicode.GetBytes($LauncherSource)
)
$PowerShell = Join-Path $PSHOME "powershell.exe"
$PowerShellArguments = "-NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand $EncodedLauncher"
$TaskAction = New-ScheduledTaskAction -Execute $PowerShell -Argument $PowerShellArguments

$WindowsIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
if ([string]::IsNullOrWhiteSpace($WindowsIdentity)) {
    throw "Could not resolve the current Windows identity for Task Scheduler."
}
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
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew

$Description = "Runs the bounded TrainCapsule V3 supervisor in WSL. Three restart attempts are enforced inside the durable supervisor; Task Scheduler does not add another restart loop."
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $ExistingTask) {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $TaskAction `
        -Trigger $Triggers `
        -Principal $Principal `
        -Settings $Settings `
        -Description $Description | Out-Null
}
else {
    Set-ScheduledTask `
        -TaskName $TaskName `
        -Action $TaskAction `
        -Trigger $Triggers `
        -Principal $Principal `
        -Settings $Settings | Out-Null
}

Write-Host "Registered Windows scheduled task: $TaskName"
Write-Host "WSL distribution: $(if ($WslDistribution) { $WslDistribution } else { '<default>' })"
Write-Host "Linux repository: $RepoPath"
Write-Host "Factory runtime: $Runtime"
Write-Host "The runtime refuses STOP, PAUSE, HARD_STUCK, stale migration, and failed preflight state."

if ($StartNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Started scheduled task."
}
