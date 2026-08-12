from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, cast

import typer
import yaml
from rich.console import Console
from rich.table import Table

from .auth import assert_max_oauth_only, subscription_credentials_path
from .autopilot import load_state, run_autopilot, save_state
from .claude_features import (
    assert_minimum_version,
    installed_claude_version,
    load_claude_features,
)
from .completion import audit_and_expand_or_complete
from .config import load_autonomy_config, load_factory_config, load_roles, load_task
from .feature_ledger import load_feature_ledger
from .github_sync import (
    load_github_config,
    load_github_state,
    sync_github,
)
from .gitops import current_sha
from .ledger import Ledger
from .models import (
    AGENT_REPORT_JSON_SCHEMA,
    FactoryConfig,
    QueueState,
    RoleName,
    TaskPacket,
    Verdict,
)
from .observability import heartbeat_health, tail_events
from .peer_messaging import peer_status as read_peer_status
from .pipeline import run_pipeline
from .queue import enqueue_task, promote_due_paused, reconcile_running, worker_loop
from .runtime_status import build_runtime_status
from .usage import usage_health
from .util import atomic_write_text, read_json, write_json
from .v3.configuration import (
    explain_v3_config_field,
    load_factory_v3,
    validate_v3_configuration,
)
from .v3.doctor import collect_doctor_report
from .v3.enums import Lane
from .v3.external_evidence import TrustedEvidenceRecord
from .v3.milestones import MilestoneRoadmap
from .v3.pilot import create_pilot_metadata, list_pilot_metadata, load_pilot_metadata
from .v3.work_items import WorkItemCollection
from .value_policy import contract_for_task, load_value_policy
from .yamlutil import load_yaml

app = typer.Typer(no_args_is_help=True, help="TrainCapsule bounded multi-agent AI factory")
config_app = typer.Typer(no_args_is_help=True, help="Validate and explain V3 configuration")
work_app = typer.Typer(no_args_is_help=True, help="Explain V3 work items")
approvals_app = typer.Typer(no_args_is_help=True, help="Inspect disabled human-approval surface")
evidence_app = typer.Typer(no_args_is_help=True, help="Validate external evidence receipts")
competitors_app = typer.Typer(no_args_is_help=True, help="Inspect competitor lane state")
pilot_app = typer.Typer(no_args_is_help=True, help="Manage local pilot metadata")
product_app = typer.Typer(no_args_is_help=True, help="Inspect the customer-local product")
app.add_typer(config_app, name="config")
app.add_typer(work_app, name="work")
app.add_typer(approvals_app, name="approvals")
app.add_typer(evidence_app, name="evidence")
app.add_typer(competitors_app, name="competitors")
app.add_typer(pilot_app, name="pilot")
app.add_typer(product_app, name="product")
console = Console()


def _resolve_repo(repo: Path) -> Path:
    return repo.expanduser().resolve()


def _v3_roadmap(repo_root: Path) -> WorkItemCollection:
    return WorkItemCollection.model_validate(
        load_yaml(repo_root / "factory/roadmap/work_items.yaml")
    )


def _v3_milestones(repo_root: Path) -> MilestoneRoadmap:
    return MilestoneRoadmap.model_validate(load_yaml(repo_root / "factory/roadmap/milestones.yaml"))


def _reject_legacy_v2_surface(repo_root: Path, config_path: Path, command: str) -> None:
    """Prevent callable V2 queue/ledger commands from mutating a V3 repository."""

    raw = load_yaml(repo_root / config_path)
    if isinstance(raw, dict) and cast(dict[str, object], raw).get("version") == 3:
        raise typer.BadParameter(
            f"{command} is a disabled V2 compatibility surface; use the V3 controller, "
            "typed roadmap, or V3 status commands"
        )


@app.command("migrate")
def migrate(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    apply: Annotated[bool, typer.Option("--apply")] = False,
    acknowledge_local_write: Annotated[bool, typer.Option("--acknowledge-local-write")] = False,
) -> None:
    """Inspect or explicitly install the deterministic, non-resuming V2 migration."""

    if dry_run == apply:
        raise typer.BadParameter("choose exactly one of --dry-run or --apply")
    if apply and not acknowledge_local_write:
        raise typer.BadParameter("--apply requires --acknowledge-local-write")
    root = _resolve_repo(repo)
    from scripts.generate_v3_legacy_migration import (
        build_mapping,
        install,
        verify_installed,
    )

    from .v3.migrations import (
        archive_stopped_legacy_queue,
        verify_stopped_legacy_queue,
    )

    migration = build_mapping(root)
    status_counts: dict[str, int] = {}
    disposition_counts: dict[str, int] = {}
    for record in migration.records:
        status_counts[record.legacy_status.value] = (
            status_counts.get(record.legacy_status.value, 0) + 1
        )
        disposition_counts[record.v3_disposition.value] = (
            disposition_counts.get(record.v3_disposition.value, 0) + 1
        )
    queue_digest, _ = verify_stopped_legacy_queue(root)
    if apply:
        install(root)
        archive = archive_stopped_legacy_queue(root)
    else:
        archive = None
    installed = True
    try:
        verify_installed(root)
    except ValueError:
        installed = False
    loaded = validate_v3_configuration(root)
    roadmap = _v3_roadmap(root)
    console.print_json(
        data={
            "dryRun": dry_run,
            "applied": apply,
            "configurationSets": sorted(loaded),
            "workItems": len(roadmap.work_items),
            "legacyRecords": len(migration.records),
            "legacyStatuses": dict(sorted(status_counts.items())),
            "legacyDispositions": dict(sorted(disposition_counts.items())),
            "legacySourceDigest": migration.source_ledger_digest,
            "legacyQueueDigest": f"sha256:{queue_digest}",
            "legacyQueueRetained": True,
            "legacyArchive": (
                archive.relative_to(root).as_posix() if archive is not None else None
            ),
            "installed": installed,
            "activeMilestone": roadmap.active_milestone,
            "mutation": apply,
        }
    )


@app.command("migrate-roadmap")
def migrate_roadmap(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    from_v2: Annotated[bool, typer.Option("--from-v2")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    apply: Annotated[bool, typer.Option("--apply")] = False,
    acknowledge_local_write: Annotated[bool, typer.Option("--acknowledge-local-write")] = False,
) -> None:
    """Migrate the historical V2 roadmap through the explicit V3 mapping."""

    if not from_v2:
        raise typer.BadParameter("roadmap migration requires --from-v2")
    migrate(
        repo=repo,
        dry_run=dry_run,
        apply=apply,
        acknowledge_local_write=acknowledge_local_write,
    )


@config_app.command("validate")
def config_validate(repo: Annotated[Path, typer.Option("--repo")] = Path(".")) -> None:
    root = _resolve_repo(repo)
    loaded = validate_v3_configuration(root)
    console.print_json(
        data={"valid": True, "version": 3, "sources": sorted(loaded), "mutation": False}
    )


@config_app.command("explain")
def config_explain(
    field: Annotated[str, typer.Argument(help="Dotted V3 field, including its config root")],
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
) -> None:
    console.print_json(data=explain_v3_config_field(_resolve_repo(repo), field))


@config_app.command("migrate")
def config_migrate(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    if not dry_run:
        raise typer.BadParameter("config migration requires --dry-run")
    root = _resolve_repo(repo)
    loaded = validate_v3_configuration(root)
    console.print_json(
        data={
            "dryRun": True,
            "alreadyV3": True,
            "files": sorted(loaded),
            "plannedWrites": [],
        }
    )


@app.command("lanes")
def lanes(repo: Annotated[Path, typer.Option("--repo")] = Path(".")) -> None:
    roadmap = _v3_roadmap(_resolve_repo(repo))
    payload: dict[str, dict[str, int]] = {}
    for lane in Lane:
        items = [item for item in roadmap.work_items if item.lane is lane]
        counts: dict[str, int] = {}
        for item in items:
            counts[item.status.value] = counts.get(item.status.value, 0) + 1
        payload[lane.value] = counts
    console.print_json(data={"activeMilestone": roadmap.active_milestone, "lanes": payload})


@app.command("milestones")
def milestones(repo: Annotated[Path, typer.Option("--repo")] = Path(".")) -> None:
    data = _v3_milestones(_resolve_repo(repo))
    console.print_json(data=data.model_dump(mode="json", by_alias=True))


@work_app.command("explain")
def work_explain(
    work_item_id: Annotated[str, typer.Argument()],
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
) -> None:
    item = _v3_roadmap(_resolve_repo(repo)).item(work_item_id)
    console.print_json(data=item.model_dump(mode="json", by_alias=True))


def _approval_root() -> Path:
    raise typer.BadParameter(
        "human approval is disabled; inspect machine policy receipts under factory state"
    )


@approvals_app.command("list")
def approvals_list() -> None:
    console.print_json(
        data={
            "interventionMode": "NONE",
            "authority": "OWNER_DIRECTED_MACHINE_POLICY_RECEIPT",
        }
    )


@approvals_app.command("show")
def approvals_show(approval_id: Annotated[str, typer.Argument()]) -> None:
    del approval_id
    _approval_root()


@approvals_app.command("record")
def approvals_record(
    signed_record: Annotated[Path, typer.Argument(help="Externally signed approval JSON")],
    acknowledge_external_write: Annotated[
        bool, typer.Option("--acknowledge-external-write")
    ] = False,
) -> None:
    del signed_record, acknowledge_external_write
    _approval_root()


@evidence_app.command("validate")
def evidence_validate(receipt: Annotated[Path, typer.Argument()]) -> None:
    record = TrustedEvidenceRecord.model_validate_json(receipt.read_text(encoding="utf-8"))
    trusted = record.require_commercial_trust()
    console.print_json(data={"valid": True, "receiptId": trusted.receipt_id})


@competitors_app.command("status")
def competitors_status(repo: Annotated[Path, typer.Option("--repo")] = Path(".")) -> None:
    items = [
        item.model_dump(mode="json", by_alias=True)
        for item in _v3_roadmap(_resolve_repo(repo)).work_items
        if item.lane is Lane.COMPETITOR
    ]
    console.print_json(data={"lane": Lane.COMPETITOR.value, "workItems": items})


@app.command("commercial-state")
def commercial_state(repo: Annotated[Path, typer.Option("--repo")] = Path(".")) -> None:
    items = [
        item.model_dump(mode="json", by_alias=True)
        for item in _v3_roadmap(_resolve_repo(repo)).work_items
        if item.lane in {Lane.MARKET, Lane.COMPETITOR}
    ]
    console.print_json(
        data={"truthBoundary": "UNKNOWN_UNLESS_TRUSTED_EXTERNAL_RECEIPT", "workItems": items}
    )


@pilot_app.command("init")
def pilot_init(
    pilot_id: Annotated[str, typer.Argument()],
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
) -> None:
    try:
        path = create_pilot_metadata(_resolve_repo(repo), pilot_id)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print_json(
        data={
            "initialized": pilot_id,
            "path": str(path),
            "immutable": True,
            "evidenceAuthority": "NONE",
            "commercialMaturity": "UNKNOWN",
        }
    )


@pilot_app.command("validate")
def pilot_validate(
    pilot_id: Annotated[str, typer.Argument()],
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
) -> None:
    try:
        path, record = load_pilot_metadata(_resolve_repo(repo), pilot_id)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print_json(
        data={
            "valid": True,
            "path": str(path),
            "pilot": record.model_dump(mode="json", by_alias=True),
        }
    )


@pilot_app.command("status")
def pilot_status(repo: Annotated[Path, typer.Option("--repo")] = Path(".")) -> None:
    try:
        records = list_pilot_metadata(_resolve_repo(repo))
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print_json(
        data={
            "pilots": [
                {
                    "path": str(path),
                    **record.model_dump(mode="json", by_alias=True),
                }
                for path, record in records
            ],
            "evidenceAuthority": "NONE",
        }
    )


@app.command("kill-gates")
def kill_gates(repo: Annotated[Path, typer.Option("--repo")] = Path(".")) -> None:
    root = _resolve_repo(repo)
    factory = load_factory_v3(root / "config/factory.yaml")
    controls = {name: (root / "factory/state" / name).exists() for name in ("STOP", "PAUSE")}
    controls["HARD_STUCK"] = (root / factory.runtime.hard_stuck_file).exists()
    console.print_json(data={"controls": controls, "mutation": False})


@product_app.command("doctor")
def product_doctor(repo: Annotated[Path, typer.Option("--repo")] = Path(".")) -> None:
    report = collect_doctor_report(_resolve_repo(repo))
    console.print_json(data=report.model_dump(mode="json", by_alias=True))
    if not report.healthy:
        raise typer.Exit(code=1)


@app.command("candidate-salvage")
def candidate_salvage(
    work_item_id: Annotated[str, typer.Argument()],
    destination: Annotated[Path, typer.Argument()],
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
) -> None:
    from .backends.fake import FakeBackend
    from .v3.controller import V3Controller

    class _DisabledPublisher:
        def prepare_candidate(self, **_: object) -> dict[str, Path]:
            raise RuntimeError("publisher is disabled for read-only salvage")

        def publish(self, **_: object) -> dict[str, object]:
            raise RuntimeError("publisher is disabled for read-only salvage")

    controller = V3Controller(
        repo_root=_resolve_repo(repo),
        backend=FakeBackend(),
        publisher=_DisabledPublisher(),
    )
    result = controller.salvage_candidate(work_item_id, destination)
    console.print_json(data={"salvaged": str(result), "mutation": "local artifact only"})


@app.command("validate-task")
def validate_task(
    task_path: Annotated[Path, typer.Argument(help="Task packet YAML")],
) -> None:
    task = load_task(task_path)
    console.print(f"[green]Valid task:[/green] {task.task_id} — {task.title}")
    console.print(f"Pipeline: {' → '.join(stage.role.value for stage in task.pipeline)}")


@app.command("run")
def run(
    task_path: Annotated[Path, typer.Argument(help="Task packet YAML")],
    repo: Annotated[Path, typer.Option("--repo", help="Target git repository")] = Path("."),
    config_path: Annotated[
        Path, typer.Option("--config", help="Factory config path relative to repo")
    ] = Path("config/factory.yaml"),
    merge: Annotated[
        bool | None,
        typer.Option("--merge/--no-merge", help="Override task auto_merge"),
    ] = None,
) -> None:
    repo_root = _resolve_repo(repo)
    _reject_legacy_v2_surface(repo_root, config_path, "run")
    config = load_factory_config(repo_root / config_path)
    task_file = task_path if task_path.is_absolute() else repo_root / task_path
    task = load_task(task_file)
    roles = load_roles(config.resolve(repo_root, config.roles_path))
    summary = asyncio.run(
        run_pipeline(
            repo_root=repo_root,
            config=config,
            task=task,
            role_configs=roles,
            merge_override=merge,
        )
    )
    console.print_json(data=summary)


@app.command("plan")
def plan(
    task_path: Annotated[Path, typer.Argument(help="Task packet YAML")],
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
) -> None:
    repo_root = _resolve_repo(repo)
    _reject_legacy_v2_surface(repo_root, config_path, "plan")
    config = load_factory_config(repo_root / config_path)
    task_file = task_path if task_path.is_absolute() else repo_root / task_path
    task = load_task(task_file)
    roles = load_roles(config.resolve(repo_root, config.roles_path))
    table = Table(title=f"Execution plan — {task.task_id} — risk: {task.risk_tier.value}")
    table.add_column("#", justify="right")
    table.add_column("Role")
    table.add_column("Model")
    table.add_column("Effort")
    table.add_column("Turns", justify="right")
    table.add_column("Est. USD-equivalent cap", justify="right")
    table.add_column("Write scope")
    total = 0.0
    for index, stage in enumerate(task.pipeline, 1):
        role = roles[stage.role]
        budget = stage.max_budget_usd or role.max_budget_usd
        total += budget
        table.add_row(
            str(index),
            stage.role.value,
            stage.model or role.model,
            stage.effort or role.effort,
            str(stage.max_turns or role.max_turns),
            f"${budget:.2f}",
            ", ".join(stage.allowed_paths) or "read-only/no writes",
        )
    console.print(table)
    console.print(
        "Worst-case initial-stage API-equivalent estimate: "
        f"[bold]${total:.2f}[/bold]; task estimate cap ${task.task_budget_usd:.2f}. "
        "These are local circuit breakers, not extra Max-plan charges."
    )


@app.command("doctor")
def doctor(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
) -> None:
    repo_root = _resolve_repo(repo)
    checks = {
        "python": sys.executable,
        "git": shutil.which("git"),
        "uv": shutil.which("uv"),
    }
    failed = False
    for name, value in checks.items():
        if value:
            console.print(f"[green]PASS[/green] {name}: {value}")
        else:
            failed = True
            console.print(f"[red]FAIL[/red] {name}: not found")

    try:
        sdk_version = importlib.metadata.version("claude-agent-sdk")
        __import__("claude_agent_sdk")
        assert_minimum_version(sdk_version, "0.2.132", "Claude Agent SDK")
        console.print(f"[green]PASS[/green] claude-agent-sdk: {sdk_version} (bundled CLI)")
    except Exception as exc:  # noqa: BLE001
        failed = True
        console.print(f"[red]FAIL[/red] claude-agent-sdk: {exc}")

    standalone = shutil.which("claude")
    if standalone:
        result = subprocess.run(
            [standalone, "--version"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        status = "PASS" if result.returncode == 0 else "WARN"
        colour = "green" if result.returncode == 0 else "yellow"
        detail = result.stdout.strip() or result.stderr.strip()
        console.print(f"[{colour}]{status}[/{colour}] standalone Claude Code: {detail}")
    else:
        console.print(
            "[yellow]INFO[/yellow] standalone `claude` not found; the pinned Agent SDK "
            "bundles its own CLI, so this is not fatal."
        )

    try:
        config = load_factory_config(repo_root / config_path)
        if config.auth_mode == "max_oauth_only":
            source = assert_max_oauth_only(
                require_long_lived_token=config.require_long_lived_oauth_for_autopilot
            )
            detail = (
                "long-lived Claude subscription OAuth token"
                if source == "oauth_env"
                else f"Claude subscription login at {subscription_credentials_path()}"
            )
            console.print(f"[green]PASS[/green] Max-only OAuth authentication: {detail}")
            console.print(
                "[cyan]INFO[/cyan] Run interactive `claude`, then `/status`, to confirm "
                "the Max account and current plan usage before the first live task."
            )
        else:
            console.print(
                "[yellow]WARN[/yellow] auth_mode is unrestricted; this package is intended "
                "for max_oauth_only."
            )
        load_roles(config.resolve(repo_root, config.roles_path))
        features = load_claude_features(config.resolve(repo_root, config.claude_features_path))
        current_cli = installed_claude_version()
        if current_cli is None:
            raise RuntimeError(
                "Standalone Claude Code is required for Claude-native feature checks"
            )
        required_cli = max(
            features.cross_session_messaging.minimum_cli_version,
            features.goal.minimum_cli_version,
            key=lambda value: tuple(int(part) for part in value.split(".")),
        )
        assert_minimum_version(current_cli, required_cli, "Configured Claude-native features")
        console.print(
            f"[green]PASS[/green] Claude-native feature floor: {current_cli}; "
            f"require >= {required_cli}"
        )
        console.print("[green]PASS[/green] factory configuration")
        if config.sandbox_enabled and sys.platform.startswith("linux"):
            for binary in ("bwrap", "socat"):
                if shutil.which(binary):
                    console.print(f"[green]PASS[/green] Linux sandbox dependency: {binary}")
                else:
                    failed = True
                    console.print(
                        f"[red]FAIL[/red] Linux sandbox dependency missing: {binary}; "
                        "fail-closed tasks will stop rather than run unsandboxed."
                    )
        if os.getenv(config.private_gate_runner_env):
            console.print(
                f"[green]PASS[/green] external private gate runner configured via "
                f"{config.private_gate_runner_env}"
            )
        else:
            console.print(
                f"[yellow]INFO[/yellow] {config.private_gate_runner_env} is unset; tasks with "
                "private_gate.required=true will fail closed."
            )
    except Exception as exc:  # noqa: BLE001
        failed = True
        console.print(f"[red]FAIL[/red] factory configuration: {exc}")
    if failed:
        raise typer.Exit(1)


@app.command("enqueue")
def enqueue(
    task_path: Annotated[Path, typer.Argument(help="Task packet YAML")],
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
    replace: Annotated[bool, typer.Option("--replace")] = False,
) -> None:
    repo_root = _resolve_repo(repo)
    _reject_legacy_v2_surface(repo_root, config_path, "enqueue")
    config = load_factory_config(repo_root / config_path)
    source = task_path if task_path.is_absolute() else repo_root / task_path
    destination = enqueue_task(repo_root=repo_root, config=config, source=source, replace=replace)
    console.print(f"[green]Enqueued[/green] {destination}")


@app.command("worker")
def worker(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
    once: Annotated[bool, typer.Option("--once")] = False,
    poll_seconds: Annotated[int | None, typer.Option("--poll-seconds")] = None,
) -> None:
    repo_root = _resolve_repo(repo)
    _reject_legacy_v2_surface(repo_root, config_path, "worker")
    config = load_factory_config(repo_root / config_path)
    asyncio.run(
        worker_loop(repo_root=repo_root, config=config, once=once, poll_seconds=poll_seconds)
    )


@app.command("queue-status")
def queue_status(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
) -> None:
    repo_root = _resolve_repo(repo)
    raw = load_yaml(repo_root / config_path)
    if isinstance(raw, dict) and cast(dict[str, object], raw).get("version") == 3:
        from .v3.queue import V3Queue

        queue = V3Queue(repo_root / "factory/queue/v3")
        counts: dict[str, int] = {}
        for item in queue.items():
            counts[item.status.value] = counts.get(item.status.value, 0) + 1
        console.print_json(data={"version": 3, "queue": counts, "mutation": False})
        return
    config = load_factory_config(repo_root / config_path)
    queue_root = config.resolve(repo_root, config.queue_dir)
    table = Table(title="TrainCapsule AI Factory queue")
    table.add_column("State")
    table.add_column("Tasks")
    for state in (
        QueueState.PENDING.value,
        QueueState.RUNNING.value,
        QueueState.PAUSED.value,
        QueueState.DONE.value,
        QueueState.FAILED.value,
        QueueState.BLOCKED.value,
    ):
        directory = queue_root / state
        tasks = sorted(path.stem for path in directory.glob("*.yaml")) if directory.exists() else []
        table.add_row(state, ", ".join(tasks) or "—")
    console.print(table)


@app.command("costs")
def costs(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
) -> None:
    repo_root = _resolve_repo(repo)
    _reject_legacy_v2_surface(repo_root, config_path, "costs")
    config = load_factory_config(repo_root / config_path)
    ledger = Ledger(config.resolve(repo_root, config.ledger_path), config.monthly_budget_usd)
    data = read_json(config.resolve(repo_root, config.ledger_path), {"runs": []})
    table = Table(title="TrainCapsule AI Factory usage-estimate ledger")
    table.add_column("Task")
    table.add_column("Run")
    table.add_column("Role")
    table.add_column("Model")
    table.add_column("Verdict")
    table.add_column("Est. USD equivalent", justify="right")
    total = 0.0
    for item in data.get("runs", []):
        cost = float(item.get("total_cost_usd", 0.0) or 0.0)
        total += cost
        table.add_row(
            str(item.get("task_id", "")),
            str(item.get("run_id", "")),
            str(item.get("role", "")),
            str(item.get("model", "")),
            str(item.get("verdict", "")),
            f"{cost:.2f}",
        )
    console.print(table)
    console.print(
        f"Current month API-equivalent estimate: [bold]${ledger.current_month_cost():.2f}[/bold] / "
        f"${ledger.monthly_budget_usd:.2f} local cap; all-time estimate ${total:.2f}. "
        "This is not billing or an authoritative reading of Max capacity."
    )


@app.command("usage-health")
def usage_health_command(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
) -> None:
    repo_root = _resolve_repo(repo)
    _reject_legacy_v2_surface(repo_root, config_path, "usage-health")
    config = load_factory_config(repo_root / config_path)
    summary = usage_health(config.resolve(repo_root, config.ledger_path))
    console.print_json(data=summary)
    if summary["status"] == "opus-heavy":
        console.print(
            "[yellow]Opus share is above the intended range. Review risk tiers and avoid "
            "using high-risk pipelines for ordinary work.[/yellow]"
        )


@app.command("github-status")
def github_status(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
) -> None:
    repo_root = _resolve_repo(repo)
    _reject_legacy_v2_surface(repo_root, config_path, "github-status")
    factory = load_factory_config(repo_root / config_path)
    config = load_github_config(factory.resolve(repo_root, factory.github_config_path))
    state = load_github_state(factory.resolve(repo_root, factory.github_state_path))
    console.print_json(
        data={"config": config.model_dump(mode="json"), "state": state.model_dump(mode="json")}
    )


@app.command("github-sync")
def github_sync_command(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    repo_root = _resolve_repo(repo)
    _reject_legacy_v2_surface(repo_root, config_path, "github-sync")
    factory = load_factory_config(repo_root / config_path)
    result = sync_github(
        repo_root=repo_root,
        config_path=factory.resolve(repo_root, factory.github_config_path),
        state_path=factory.resolve(repo_root, factory.github_state_path),
        task=None,
        reason="manual synchronization",
        force=force,
    )
    console.print_json(data=result)


@app.command("schema")
def schema(
    output: Annotated[Path, typer.Option("--output")] = Path("schemas/task.generated.json"),
) -> None:
    write_json(output, TaskPacket.model_json_schema())
    write_json(output.with_name("agent-report.generated.json"), AGENT_REPORT_JSON_SCHEMA)
    console.print(f"Wrote schemas to {output.parent}")


@app.command("v3-schedule")
def v3_schedule(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    explain: Annotated[bool, typer.Option("--explain")] = False,
) -> None:
    """Simulate one deterministic V3 scheduler cycle without mutating the queue."""

    if not dry_run:
        console.print("[red]Refused.[/red] V3 scheduling is simulation-only until M0 closes.")
        raise typer.Exit(2)
    from tcfactory.v3.configuration import load_factory_v3, load_scheduler_v3
    from tcfactory.v3.scheduler import schedule_cycle
    from tcfactory.v3.work_items import WorkItemCollection

    repo_root = _resolve_repo(repo)
    factory = load_factory_v3(repo_root / "config/factory.yaml")
    scheduler = load_scheduler_v3(repo_root / "config/scheduler.yaml")
    work_items = WorkItemCollection.model_validate(
        load_yaml(repo_root / factory.roadmap.work_items)
    )
    decided_at = datetime.now(UTC)
    artifact = schedule_cycle(
        work_items,
        scheduler,
        cycle_id=f"dry-run-{decided_at.strftime('%Y%m%dT%H%M%SZ')}",
        decided_at=decided_at,
        max_concurrent_mutating_sessions=(factory.execution.max_concurrent_mutating_sessions),
        max_concurrent_read_only_sessions=(factory.execution.max_concurrent_read_only_sessions),
    )
    if explain:
        console.print_json(
            data={
                "cycleId": artifact.cycle_id,
                "activeMilestone": artifact.active_milestone,
                "configDigest": artifact.config_digest,
                "selectedWorkItemIds": artifact.selected_work_item_ids,
                "evaluations": [
                    {
                        "workItemId": item.work_item_id,
                        "lane": item.lane.value,
                        "eligible": item.eligible,
                        "score": item.score,
                        "reasons": item.reasons,
                    }
                    for item in artifact.evaluations
                    if work_items.item(item.work_item_id).milestone == scheduler.active_milestone
                ],
            }
        )
    else:
        selected = artifact.selected_work_item_ids or ["none"]
        console.print(f"Selected: {', '.join(selected)}")


@app.command("status")
def status(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
) -> None:
    repo_root = _resolve_repo(repo)
    console.print_json(data=build_runtime_status(repo_root))


@app.command("autopilot")
def autopilot_command(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
    autonomy_path: Annotated[Path | None, typer.Option("--autonomy-config")] = None,
    once: Annotated[bool, typer.Option("--once")] = False,
) -> None:
    """Compatibility spelling for the V3-only unattended controller."""
    del config_path, autonomy_path
    v3_controller(repo=repo, once=once)


@app.command("v3-controller")
def v3_controller(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    once: Annotated[bool, typer.Option("--once")] = False,
) -> None:
    """Run the V3 work-item scheduler and exact-SHA main-only release controller."""

    from .backends.claude import ClaudeBackend
    from .github_sync import MainOnlyPublisher
    from .v3.controller import V3Controller

    root = _resolve_repo(repo)
    validate_v3_configuration(root)
    github = load_github_config(root / "config/github.yaml")
    runtime_root_value = os.getenv("TCF_RUNTIME_ROOT")
    runtime_root = (
        Path(runtime_root_value).expanduser().resolve()
        if runtime_root_value
        else (root / "factory/state").resolve()
    )
    publisher = MainOnlyPublisher(
        repo_root=root,
        config=github,
        receipt_root=runtime_root / "machine-policy-receipts",
        quarantine_root=runtime_root / "quarantine",
    )
    controller = V3Controller(
        repo_root=root,
        backend=ClaudeBackend(),
        publisher=publisher,
    )

    async def execute() -> None:
        while True:
            result = await controller.run_cycle()
            console.print_json(data=result)
            if once:
                return
            if (runtime_root / "STOP").exists() or (runtime_root / "PAUSE").exists():
                return
            await asyncio.sleep(30 if result.get("status") == "IDLE" else 2)

    asyncio.run(execute())


@app.command("autonomy-enable")
def autonomy_enable(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
    acknowledge: Annotated[bool, typer.Option("--acknowledge")] = False,
) -> None:
    """Enable automatic planning, merging, quota resume, and restart recovery after calibration."""
    if not acknowledge:
        console.print("[red]Refused.[/red] Re-run with --acknowledge after calibration passes.")
        raise typer.Exit(2)
    repo_root = _resolve_repo(repo)
    _reject_legacy_v2_surface(repo_root, config_path, "autonomy-enable")
    factory = load_factory_config(repo_root / config_path)
    try:
        assert_max_oauth_only(
            require_long_lived_token=factory.require_long_lived_oauth_for_autopilot
        )
    except RuntimeError as exc:
        console.print(f"[red]Long-lived Max OAuth is not ready:[/red] {exc}")
        raise typer.Exit(2) from exc
    if factory.max_parallel != 1:
        console.print("[red]Refused.[/red] Lights-out mode requires one serial worker.")
        raise typer.Exit(2)
    private_runner = os.getenv(factory.private_gate_runner_env)
    if not private_runner or not os.access(Path(private_runner).expanduser(), os.X_OK):
        console.print(
            f"[red]Refused.[/red] {factory.private_gate_runner_env} must point to an "
            "executable external private gate before autonomy is enabled."
        )
        raise typer.Exit(2)
    path = factory.resolve(repo_root, factory.autonomy_config_path)
    payload = load_yaml(path)
    marker = repo_root / str(payload.get("calibration_marker", "factory/state/CALIBRATION_PASSED"))
    if payload.get("require_calibration", True) and not marker.exists():
        console.print(f"[red]Calibration marker missing:[/red] {marker}")
        raise typer.Exit(2)
    payload["enabled"] = True
    atomic_write_text(path, yaml.safe_dump(payload, sort_keys=False))
    console.print(
        f"[yellow]Autonomy enablement is a reviewable local diff; it was not committed.[/yellow] "
        f"{path}"
    )


def _json_object(text: str, label: str) -> dict[str, object]:
    value: object = json.loads(text)
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be a JSON object")
    return cast(dict[str, object], value)


def _object_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise RuntimeError(f"{label} must be a JSON array")
    return cast(list[object], value)


def validate_calibration_evidence(repo_root: Path) -> dict[str, object]:
    evidence_path = repo_root / "factory/state/CALIBRATION_EVIDENCE.json"
    if not evidence_path.is_file():
        raise RuntimeError(f"Calibration evidence is missing: {evidence_path}")
    try:
        evidence = _json_object(evidence_path.read_text(encoding="utf-8"), "Calibration evidence")
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Calibration evidence is unreadable: {exc}") from exc
    version = evidence.get("version")
    if not isinstance(version, int) or version < 3:
        raise RuntimeError("Calibration evidence must be a version-3 JSON object")

    required = {
        "max_oauth_verify",
        "schema_generation",
        "unit_tests",
        "ruff",
        "pyright",
        "deterministic_sabotage",
        "private_gate_self_test",
        "private_gate_repository",
        "live_demo",
        "claude_native_features",
        "cross_session_messaging",
    }
    claimed = {
        str(value)
        for value in _object_list(
            evidence.get("required_controls", []), "Calibration required controls"
        )
    }
    missing = sorted(required - claimed)
    if missing:
        raise RuntimeError(f"Calibration evidence is missing required controls: {missing}")

    log_entries = _object_list(evidence.get("logs"), "Calibration logs")
    if not log_entries:
        raise RuntimeError("Calibration evidence contains no hashed log files")
    logged_names: set[str] = set()
    for entry in log_entries:
        if not isinstance(entry, dict):
            raise RuntimeError("Calibration log entry is not an object")
        entry = cast(dict[str, object], entry)
        raw_path = str(entry.get("path") or "")
        path = (repo_root / raw_path).resolve()
        try:
            path.relative_to(repo_root)
        except ValueError as exc:
            raise RuntimeError(f"Calibration log escapes the repository: {raw_path}") from exc
        if not path.is_file():
            raise RuntimeError(f"Calibration log is missing: {raw_path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != str(entry.get("sha256") or ""):
            raise RuntimeError(f"Calibration log digest mismatch: {raw_path}")
        logged_names.add(path.name.split(".", 1)[0])
    if not required.issubset(logged_names):
        raise RuntimeError(
            "Calibration evidence does not contain logs for every required control: "
            f"{sorted(required - logged_names)}"
        )

    summary_raw = str(evidence.get("live_pipeline_summary") or "")
    summary_path = (repo_root / summary_raw).resolve()
    try:
        summary_path.relative_to(repo_root)
    except ValueError as exc:
        raise RuntimeError("Live calibration summary escapes the repository") from exc
    if not summary_path.is_file():
        raise RuntimeError(f"Live calibration summary is missing: {summary_raw}")
    if hashlib.sha256(summary_path.read_bytes()).hexdigest() != str(
        evidence.get("summary_sha256") or ""
    ):
        raise RuntimeError("Live calibration summary digest mismatch")
    try:
        summary = _json_object(summary_path.read_text(encoding="utf-8"), "Live calibration summary")
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Live calibration summary is unreadable: {exc}") from exc
    head = current_sha(repo_root)
    if str(evidence.get("head_sha") or "") != head or summary.get("starting_sha") != head:
        raise RuntimeError("Calibration was not executed against the current main HEAD")
    if summary.get("merged") is not False or not summary.get("final_sha"):
        raise RuntimeError("Calibration demo must pass without merging and produce a candidate SHA")
    results = _object_list(summary.get("results"), "Calibration role results")
    if not results:
        raise RuntimeError("Calibration demo contains no role results")
    typed_results = [cast(dict[str, object], item) for item in results if isinstance(item, dict)]
    required_roles = {"specification", "builder", "adversary", "audit", "release"}
    roles = {str(item.get("role")) for item in typed_results}
    if not required_roles.issubset(roles):
        raise RuntimeError(f"Calibration demo is missing roles: {sorted(required_roles - roles)}")
    if len(typed_results) != len(results) or any(
        item.get("verdict") != "pass" for item in typed_results
    ):
        raise RuntimeError("At least one calibration role did not return PASS")

    builder = next(
        (item for item in typed_results if item.get("role") == RoleName.BUILDER.value),
        None,
    )
    if builder is None or builder.get("peer_messaging_enabled") is not True:
        raise RuntimeError("Calibration builder did not enable cross-session messaging")
    peer_sessions = _object_list(builder.get("peer_sessions", []), "Builder peer sessions")
    typed_peer_sessions = [
        cast(dict[str, object], item) for item in peer_sessions if isinstance(item, dict)
    ]
    scout = next(
        (
            item
            for item in typed_peer_sessions
            if item.get("role") == RoleName.INTEGRATION_SCOUT.value
        ),
        None,
    )
    if scout is None or scout.get("verdict") != Verdict.PASS.value:
        raise RuntimeError("Calibration integration scout did not return PASS")

    session_ids = [str(item.get("session_id")) for item in typed_results if item.get("session_id")]
    if scout.get("session_id"):
        session_ids.append(str(scout["session_id"]))
    if len(session_ids) < len(required_roles) + 1 or len(session_ids) != len(set(session_ids)):
        raise RuntimeError("Calibration roles and scout must use distinct Claude sessions")

    def _artifact_dir(raw: object, label: str) -> Path:
        candidate = Path(str(raw or ""))
        path = candidate.resolve() if candidate.is_absolute() else (repo_root / candidate).resolve()
        try:
            path.relative_to(repo_root)
        except ValueError as exc:
            raise RuntimeError(f"{label} artifact directory escapes the repository") from exc
        if not path.is_dir():
            raise RuntimeError(f"{label} artifact directory is missing: {path}")
        return path

    builder_dir = _artifact_dir(builder.get("artifact_dir"), "Builder")
    scout_dir = _artifact_dir(scout.get("artifact_dir"), "Integration scout")
    for label, directory in (("Builder", builder_dir), ("Integration scout", scout_dir)):
        message_audit = directory / "peer-messages.jsonl"
        if not message_audit.is_file() or not message_audit.read_text(encoding="utf-8").strip():
            raise RuntimeError(f"{label} produced no cross-session message audit")
        feature_plan_path = directory / "claude-native-feature-plan.json"
        if not feature_plan_path.is_file():
            raise RuntimeError(f"{label} Claude-native feature plan is missing")

    try:
        builder_plan = _json_object(
            (builder_dir / "claude-native-feature-plan.json").read_text(encoding="utf-8"),
            "Builder Claude-native feature plan",
        )
        scout_plan = _json_object(
            (scout_dir / "claude-native-feature-plan.json").read_text(encoding="utf-8"),
            "Scout Claude-native feature plan",
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Claude-native feature plan is invalid: {exc}") from exc
    builder_skills = _object_list(builder_plan.get("skills", []), "Builder skills")
    scout_skills = _object_list(scout_plan.get("skills", []), "Scout skills")
    if (
        builder_plan.get("peer_messaging") is not True
        or not builder_plan.get("goal_condition")
        or builder_plan.get("advisor_model") != "opus"
        or "implement-task" not in builder_skills
    ):
        raise RuntimeError(
            "Calibration builder did not exercise the required Claude-native features"
        )
    if scout_plan.get("peer_messaging") is not True or "integration-proof" not in scout_skills:
        raise RuntimeError("Calibration scout did not exercise the required Claude-native features")
    return evidence


@app.command("mark-calibrated")
def mark_calibrated(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
    acknowledge: Annotated[bool, typer.Option("--acknowledge")] = False,
) -> None:
    """Create the one-time calibration marker only after verifiable evidence passes."""
    if not acknowledge:
        console.print(
            "[red]Refused.[/red] Re-run with --acknowledge only after calibration evidence passes."
        )
        raise typer.Exit(2)
    repo_root = _resolve_repo(repo)
    _reject_legacy_v2_surface(repo_root, config_path, "mark-calibrated")
    factory = load_factory_config(repo_root / config_path)
    try:
        evidence = validate_calibration_evidence(repo_root)
    except RuntimeError as exc:
        console.print(f"[red]Calibration evidence rejected:[/red] {exc}")
        raise typer.Exit(2) from exc
    autonomy = load_autonomy_config(factory.resolve(repo_root, factory.autonomy_config_path))
    marker = repo_root / autonomy.calibration_marker
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        "Calibration passed with hashed deterministic, private-gate, and live multi-role "
        "evidence.\n"
        f"Evidence: factory/state/CALIBRATION_EVIDENCE.json\n"
        f"Head: {evidence['head_sha']}\n",
        encoding="utf-8",
    )
    console.print(f"[green]Calibration marker created.[/green] {marker}")


@app.command("autonomy-status")
def autonomy_status(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
) -> None:
    repo_root = _resolve_repo(repo)
    _reject_legacy_v2_surface(repo_root, config_path, "autonomy-status")
    factory = load_factory_config(repo_root / config_path)
    autonomy = load_autonomy_config(factory.resolve(repo_root, factory.autonomy_config_path))
    state = load_state(repo_root, factory)
    console.print_json(
        data={
            "configuration": autonomy.model_dump(mode="json"),
            "state": state.model_dump(mode="json"),
        }
    )


def _control_file(repo_root: Path, factory: FactoryConfig, name: str) -> Path:
    autonomy = load_autonomy_config(factory.resolve(repo_root, factory.autonomy_config_path))
    value = autonomy.stop_file if name == "stop" else autonomy.pause_file
    return repo_root / value


@app.command("autonomy-pause")
def autonomy_pause(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
) -> None:
    repo_root = _resolve_repo(repo)
    factory = load_factory_config(repo_root / config_path)
    path = _control_file(repo_root, factory, "pause")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("pause requested\n", encoding="utf-8")
    console.print(f"[yellow]Autopilot pause requested.[/yellow] {path}")


@app.command("autonomy-resume")
def autonomy_resume(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
) -> None:
    repo_root = _resolve_repo(repo)
    factory = load_factory_config(repo_root / config_path)
    autonomy = load_autonomy_config(factory.resolve(repo_root, factory.autonomy_config_path))
    stop_path = _control_file(repo_root, factory, "stop")
    hard_stuck_path = repo_root / autonomy.hard_stuck_path
    roadmap = _v3_roadmap(repo_root)
    protected_states = {
        "REJECTED_VALUE",
        "NATIVE_SUFFICIENT",
        "CANCELLED",
    }
    blockers = [
        item.work_item_id
        for item in roadmap.work_items
        if item.status.value in protected_states and item.milestone == roadmap.active_milestone
    ]
    if stop_path.exists() or hard_stuck_path.exists() or blockers:
        console.print(
            "[red]Refused.[/red] Generic resume cannot clear STOP/HARD_STUCK or protected "
            f"work dispositions; blockers={blockers}. Use deterministic machine-policy recovery."
        )
        raise typer.Exit(2)
    _control_file(repo_root, factory, "pause").unlink(missing_ok=True)
    state = load_state(repo_root, factory)
    state.repair_attempts = 0
    state.repair_status = None
    state.blocker_reason = None
    state.required_action = None
    state.blocked_tasks = []
    state.last_repair_artifact = None
    state.next_wake_at = None
    state.status = "restarting"
    state.current_action = "retry requested"
    save_state(repo_root, factory, state)
    console.print("[green]Autopilot controls cleared; service may resume.[/green]")


@app.command("autonomy-stop")
def autonomy_stop(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
) -> None:
    repo_root = _resolve_repo(repo)
    factory = load_factory_config(repo_root / config_path)
    path = _control_file(repo_root, factory, "stop")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("stop requested\n", encoding="utf-8")
    console.print(f"[red]Autopilot stop requested.[/red] {path}")


@app.command("completion-audit")
def completion_audit(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
) -> None:
    """Run the independent product-completion audit or expand the roadmap."""
    repo_root = _resolve_repo(repo)
    _reject_legacy_v2_surface(repo_root, config_path, "completion-audit")
    factory = load_factory_config(repo_root / config_path)
    autonomy = load_autonomy_config(factory.resolve(repo_root, factory.autonomy_config_path))
    ledger = load_feature_ledger(factory.resolve(repo_root, factory.feature_ledger_path))
    outcome, evidence, audited_sha = asyncio.run(
        audit_and_expand_or_complete(
            repo_root=repo_root,
            config=factory,
            ledger=ledger,
            audits_required=autonomy.completion_audits_required,
        )
    )
    console.print_json(data={"outcome": outcome, "evidence": evidence, "audited_sha": audited_sha})


@app.command("autonomy-disable")
def autonomy_disable(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
) -> None:
    """Disable future automatic work and request the current autopilot to stop cleanly."""
    repo_root = _resolve_repo(repo)
    _reject_legacy_v2_surface(repo_root, config_path, "autonomy-disable")
    factory = load_factory_config(repo_root / config_path)
    path = factory.resolve(repo_root, factory.autonomy_config_path)
    payload = load_yaml(path)
    payload["enabled"] = False
    atomic_write_text(path, yaml.safe_dump(payload, sort_keys=False))
    stop_path = _control_file(repo_root, factory, "stop")
    stop_path.parent.mkdir(parents=True, exist_ok=True)
    stop_path.write_text("autonomy disabled\n", encoding="utf-8")
    console.print(
        "[yellow]Lights-out autonomy disabled as a reviewable local diff; "
        "no commit was made.[/yellow]"
    )


@app.command("queue-reconcile")
def queue_reconcile(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
) -> None:
    repo_root = _resolve_repo(repo)
    _reject_legacy_v2_surface(repo_root, config_path, "queue-reconcile")
    factory = load_factory_config(repo_root / config_path)
    recovered = reconcile_running(repo_root, factory)
    due = promote_due_paused(repo_root, factory)
    console.print(f"Recovered {recovered} interrupted tasks; resumed {due} due quota pauses.")


@app.command("start")
def start(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
    once: Annotated[bool, typer.Option("--once")] = False,
) -> None:
    """Clear pause/stop controls and run the autonomous loop in the foreground."""
    repo_root = _resolve_repo(repo)
    factory = load_factory_config(repo_root / config_path)
    if _control_file(repo_root, factory, "stop").exists():
        console.print(
            "[red]Refused.[/red] Generic start cannot clear STOP; use an explicit recovery "
            "decision with an immutable override record."
        )
        raise typer.Exit(2)
    _control_file(repo_root, factory, "pause").unlink(missing_ok=True)
    asyncio.run(
        run_autopilot(
            repo_root=repo_root,
            factory_config_path=config_path,
            autonomy_config_path=None,
            once=once,
        )
    )


@app.command("pause")
def pause_alias(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
) -> None:
    """Request a safe-boundary pause."""
    autonomy_pause(repo=repo, config_path=config_path)


@app.command("resume")
def resume_alias(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
) -> None:
    """Clear pause/stop controls; the scheduled service resumes automatically."""
    autonomy_resume(repo=repo, config_path=config_path)


@app.command("stop")
def stop_alias(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
) -> None:
    """Request a clean stop."""
    autonomy_stop(repo=repo, config_path=config_path)


@app.command("verify")
def verify_factory(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
) -> None:
    """Show one machine-readable health snapshot without changing factory state."""
    repo_root = _resolve_repo(repo)
    factory = load_factory_config(repo_root / config_path)
    autonomy = load_autonomy_config(factory.resolve(repo_root, factory.autonomy_config_path))
    state = load_state(repo_root, factory)
    marker = repo_root / autonomy.calibration_marker
    private_runner = os.getenv(factory.private_gate_runner_env)
    auth_ok = True
    auth_detail = "ok"
    try:
        assert_max_oauth_only(
            require_long_lived_token=factory.require_long_lived_oauth_for_autopilot
        )
    except RuntimeError as exc:
        auth_ok = False
        auth_detail = str(exc)
    heartbeat = heartbeat_health(
        factory.resolve(repo_root, factory.heartbeat_path),
        stale_after_seconds=max(300, autonomy.heartbeat_seconds * 5),
    )
    payload = {
        "version": "8.0.0",
        "repo": str(repo_root),
        "git_head": current_sha(repo_root),
        "clean_main": not bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_root,
                text=True,
                capture_output=True,
                check=False,
            ).stdout.strip()
        ),
        "autonomy_enabled": autonomy.enabled,
        "autonomy_state": state.model_dump(mode="json"),
        "calibrated": marker.is_file(),
        "max_oauth_only": auth_ok,
        "auth_detail": auth_detail,
        "private_gate_executable": bool(
            private_runner and os.access(Path(private_runner).expanduser(), os.X_OK)
        ),
        "heartbeat": heartbeat,
        "github": load_github_state(
            factory.resolve(repo_root, factory.github_state_path)
        ).model_dump(mode="json"),
    }
    payload["healthy"] = all(
        [
            payload["calibrated"],
            payload["max_oauth_only"],
            payload["private_gate_executable"],
            not heartbeat.get("stale", True),
        ]
    )
    console.print_json(data=payload)
    if not payload["healthy"]:
        raise typer.Exit(1)


@app.command("logs")
def logs(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
    limit: Annotated[int, typer.Option("--limit", min=1, max=1000)] = 100,
) -> None:
    """Print compact controller events and recent autopilot log lines."""
    repo_root = _resolve_repo(repo)
    factory = load_factory_config(repo_root / config_path)
    events = tail_events(factory.resolve(repo_root, factory.event_log_path), limit=limit)
    console.print_json(data={"events": events})
    path = repo_root / "factory/logs/autopilot.log"
    if path.is_file():
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
        console.print("\n".join(lines))


@app.command("roadmap")
def roadmap(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
) -> None:
    """Show roadmap counts and the next dependency-ready task."""
    repo_root = _resolve_repo(repo)
    raw = load_yaml(repo_root / config_path)
    if isinstance(raw, dict) and cast(dict[str, object], raw).get("version") == 3:
        collection = _v3_roadmap(repo_root)
        counts: dict[str, int] = {}
        for item in collection.work_items:
            counts[item.status.value] = counts.get(item.status.value, 0) + 1
        current = next(
            (
                item
                for item in collection.work_items
                if item.milestone == collection.active_milestone
                and item.status.value not in {"COMPLETED", "CANCELLED", "DEFERRED"}
            ),
            None,
        )
        console.print_json(
            data={
                "version": 3,
                "activeMilestone": collection.active_milestone,
                "counts": counts,
                "next": None if current is None else current.model_dump(mode="json", by_alias=True),
                "mutation": False,
            }
        )
        return
    factory = load_factory_config(repo_root / config_path)
    ledger = load_feature_ledger(factory.resolve(repo_root, factory.feature_ledger_path))
    ledger.refresh_readiness()
    counts: dict[str, int] = {}
    for item in ledger.tasks:
        counts[item.status] = counts.get(item.status, 0) + 1
    next_item = ledger.next_ready()
    console.print_json(
        data={
            "counts": counts,
            "next": None if next_item is None else next_item.model_dump(mode="json"),
            "build_complete": ledger.build_complete(),
            "all_automatable_complete": ledger.all_automatable_complete(),
        }
    )


@app.command("value-status")
def value_status(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
    task_id: Annotated[str | None, typer.Option("--task-id")] = None,
) -> None:
    """Show frozen customer-value contracts without inventing external demand evidence."""
    repo_root = _resolve_repo(repo)
    factory = load_factory_config(repo_root / config_path)
    policy = load_value_policy(factory.resolve(repo_root, factory.value_policy_path))
    ids = [task_id] if task_id else sorted(policy.tasks)
    rows: list[dict[str, object]] = []
    for value in ids:
        try:
            contract = contract_for_task(policy, value)
        except Exception as exc:  # noqa: BLE001
            rows.append({"task_id": value, "error": str(exc)})
            continue
        evidence = repo_root / (contract.evidence_path or "") if contract.evidence_path else None
        rows.append(
            {
                "task_id": value,
                "mode": contract.mode.value,
                "target_user": contract.target_user,
                "customer_outcome": contract.customer_outcome,
                "primary_metric": contract.primary_metric,
                "threshold": contract.minimum_material_improvement,
                "evidence_path": contract.evidence_path,
                "evidence_present": bool(evidence and evidence.is_file()),
                "revenue_linkage": contract.revenue_linkage,
            }
        )
    console.print_json(data={"contracts": rows})


@app.command("peer-status")
def peer_status_command(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
    task_id: Annotated[str | None, typer.Option("--task-id")] = None,
) -> None:
    """Show cross-session peers and bounded message counts."""
    repo_root = _resolve_repo(repo)
    _reject_legacy_v2_surface(repo_root, config_path, "peer-status")
    factory = load_factory_config(repo_root / config_path)
    console.print_json(
        data=read_peer_status(factory.resolve(repo_root, factory.peer_message_dir), task_id)
    )


@app.command("features")
def features_command(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
) -> None:
    """Show the Claude-native feature policy and token-conscious defaults."""
    repo_root = _resolve_repo(repo)
    factory = load_factory_config(repo_root / config_path)
    features = load_claude_features(factory.resolve(repo_root, factory.claude_features_path))
    console.print_json(data=features.model_dump(mode="json"))


@app.command("explain-blocker")
def explain_blocker(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
) -> None:
    """Explain the latest durable blocker using controller state and artifacts only."""
    repo_root = _resolve_repo(repo)
    raw = load_yaml(repo_root / config_path)
    if isinstance(raw, dict) and cast(dict[str, object], raw).get("version") == 3:
        console.print_json(data=build_runtime_status(repo_root))
        return
    factory = load_factory_config(repo_root / config_path)
    state = load_state(repo_root, factory)
    failed = sorted((factory.resolve(repo_root, factory.queue_dir) / "failed").glob("*.yaml"))
    blocked = sorted((factory.resolve(repo_root, factory.queue_dir) / "blocked").glob("*.yaml"))
    recent = tail_events(factory.resolve(repo_root, factory.event_log_path), limit=25)
    console.print_json(
        data={
            "state": state.model_dump(mode="json"),
            "failed_tasks": [path.stem for path in failed],
            "blocked_tasks": [path.stem for path in blocked],
            "recent_events": recent,
        }
    )


@app.command("recover")
def recover(
    repo: Annotated[Path, typer.Option("--repo")] = Path("."),
    config_path: Annotated[Path, typer.Option("--config")] = Path("config/factory.yaml"),
) -> None:
    """Reconcile interrupted queue state and promote quota pauses whose reset has passed."""
    repo_root = _resolve_repo(repo)
    _reject_legacy_v2_surface(repo_root, config_path, "recover")
    factory = load_factory_config(repo_root / config_path)
    recovered = reconcile_running(repo_root, factory)
    resumed = promote_due_paused(repo_root, factory)
    console.print_json(data={"recovered_interrupted": recovered, "resumed_due_pauses": resumed})


if __name__ == "__main__":
    app()
