$ErrorActionPreference = "Stop"
powercfg.exe /change standby-timeout-ac 0 | Out-Null
powercfg.exe /change hibernate-timeout-ac 0 | Out-Null
Write-Host "AC sleep and hibernate timeouts set to Never for the current power plan."
