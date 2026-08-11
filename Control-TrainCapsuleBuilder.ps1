[CmdletBinding()]
param(
    [ValidateSet(
        "Overview", "Start", "Pause", "Resume", "Stop", "Verify", "Recover", "Logs",
        "Queue", "Costs", "Roadmap", "Value", "Peers", "Blocker", "Features", "GitHub", "Sync"
    )]
    [string]$Action = "Overview",
    [ValidatePattern('^T\d{3}$')]
    [string]$TaskId = "T001"
)

$distribution = "Ubuntu-22.04"
$repository = "/home/jasim/projects/traincapsule"
$scheduledTask = "TrainCapsule Factory Autopilot"
$factoryShell = "cd '$repository' && source scripts/load_factory_env.sh &&"

switch ($Action) {
    "Start" {
        $task = Get-ScheduledTask -TaskName $scheduledTask -ErrorAction SilentlyContinue
        if ($null -ne $task) {
            Start-ScheduledTask -TaskName $scheduledTask
        } else {
            & wsl.exe -d $distribution -- bash -lc "cd '$repository' && bash scripts/windows_task_entrypoint.sh"
        }
    }
    "Pause" {
        & wsl.exe -d $distribution -- bash -lc "$factoryShell uv run tcfactory pause"
    }
    "Resume" {
        & wsl.exe -d $distribution -- bash -lc "$factoryShell uv run tcfactory resume"
    }
    "Stop" {
        & wsl.exe -d $distribution -- bash -lc "$factoryShell uv run tcfactory stop"
    }
    "Verify" {
        & wsl.exe -d $distribution -- bash -lc "$factoryShell uv run tcfactory verify"
    }
    "Recover" {
        & wsl.exe -d $distribution -- bash -lc "$factoryShell uv run tcfactory recover"
    }
    "Logs" {
        & wsl.exe -d $distribution -- bash -lc "$factoryShell uv run tcfactory logs"
    }
    "Queue" {
        & wsl.exe -d $distribution -- bash -lc "$factoryShell uv run tcfactory queue-status"
    }
    "Costs" {
        & wsl.exe -d $distribution -- bash -lc "$factoryShell uv run tcfactory costs"
    }
    "Roadmap" {
        & wsl.exe -d $distribution -- bash -lc "$factoryShell uv run tcfactory roadmap"
    }
    "Value" {
        & wsl.exe -d $distribution -- bash -lc "$factoryShell uv run tcfactory value-status --task-id '$TaskId'"
    }
    "Peers" {
        & wsl.exe -d $distribution -- bash -lc "$factoryShell uv run tcfactory peer-status"
    }
    "Blocker" {
        & wsl.exe -d $distribution -- bash -lc "$factoryShell uv run tcfactory explain-blocker"
    }
    "Features" {
        & wsl.exe -d $distribution -- bash -lc "$factoryShell uv run tcfactory features"
    }
    "GitHub" {
        & wsl.exe -d $distribution -- bash -lc "$factoryShell uv run tcfactory github-status"
    }
    "Sync" {
        & wsl.exe -d $distribution -- bash -lc "$factoryShell uv run tcfactory github-sync"
    }
    "Overview" {
        & wsl.exe -d $distribution -- bash -lc "$factoryShell uv run tcfactory status"
    }
}
