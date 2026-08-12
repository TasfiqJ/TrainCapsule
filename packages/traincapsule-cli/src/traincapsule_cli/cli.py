"""Offline-first TrainCapsule product CLI."""

from __future__ import annotations

import json
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Annotated, NoReturn, cast

import typer
from pydantic import BaseModel, ValidationError
from traincapsule_core import (
    IncidentCase,
    build_environment_identity,
    build_workload_identity,
    canonical_json_bytes,
)
from traincapsule_core.evidence import EvidenceStoreError, LocalEvidenceStore
from traincapsule_core.models import CaseEconomics
from traincapsule_ingest_pytorch import (
    FlightRecorderImportError,
    ImportErrorCode,
    PyTorchFlightRecorderImporter,
)
from traincapsule_qualify import NativeBaseline, PreflightInputs, evaluate_preflight

app = typer.Typer(no_args_is_help=True, help="Customer-local TrainCapsule product tools.")
case_app = typer.Typer(no_args_is_help=True, help="Create and inspect incident cases.")
ingest_app = typer.Typer(no_args_is_help=True, help="Import customer-local evidence.")
identity_app = typer.Typer(no_args_is_help=True, help="Build deterministic identities.")
app.add_typer(case_app, name="case")
app.add_typer(ingest_app, name="ingest")
app.add_typer(identity_app, name="identity")

_MAX_CONTROL_FILE_BYTES = 4 * 1024 * 1024


class ExitCode(IntEnum):
    OK = 0
    INVALID_INPUT = 2
    UNSUPPORTED_VERSION = 3
    POLICY_BLOCKED = 4
    LOCAL_IO_ERROR = 5


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("timestamp must be ISO 8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include an explicit UTC offset")
    return parsed


def _read_object(path: Path) -> dict[str, object]:
    if path.is_symlink():
        raise ValueError("input cannot be a symlink")
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("input must be a regular file")
    if resolved.stat().st_size > _MAX_CONTROL_FILE_BYTES:
        raise ValueError("input exceeds the local control-file limit")
    raw: object = json.loads(resolved.read_bytes())
    if not isinstance(raw, dict):
        raise ValueError("input JSON must be an object")
    return cast(dict[str, object], raw)


def _machine_message(*, ok: bool, code: str, message: str) -> bytes:
    return canonical_json_bytes({"code": code, "message": message, "ok": ok})


def _fail(
    message: str,
    *,
    code: ExitCode,
    machine: bool,
    error_code: str | None = None,
) -> NoReturn:
    if machine:
        typer.echo(
            _machine_message(
                ok=False,
                code=error_code or code.name,
                message=message,
            ).decode("utf-8"),
            nl=False,
            err=True,
        )
    else:
        typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(int(code))


def _write_result(
    value: BaseModel | dict[str, object],
    *,
    output: Path | None,
    machine: bool,
) -> None:
    if isinstance(value, BaseModel):
        payload: object = value.model_dump(mode="json", by_alias=True, exclude_none=False)
    else:
        payload = value
    rendered = canonical_json_bytes(payload)
    if output is None:
        typer.echo(rendered.decode("utf-8"), nl=False)
        return
    if output.exists() or output.is_symlink():
        _fail(
            f"output already exists: {output}",
            code=ExitCode.LOCAL_IO_ERROR,
            machine=machine,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    if any(parent.is_symlink() for parent in (output.parent, *output.parent.parents)):
        _fail(
            "output path contains a symlink",
            code=ExitCode.POLICY_BLOCKED,
            machine=machine,
        )
    output.write_bytes(rendered)
    if machine:
        typer.echo(
            _machine_message(ok=True, code="OK", message=str(output.resolve())).decode(
                "utf-8"
            ),
            nl=False,
        )
    else:
        typer.echo(f"Wrote {output.resolve()}")


@app.command("doctor")
def doctor(
    machine: Annotated[bool, typer.Option("--json", help="Emit canonical JSON.")] = False,
) -> None:
    result: dict[str, object] = {
        "checks": {
            "networkRequired": False,
            "productPackages": "available",
            "python": "3.12",
        },
        "ok": True,
        "productSchemaVersion": 1,
    }
    if machine:
        typer.echo(canonical_json_bytes(result).decode("utf-8"), nl=False)
    else:
        typer.echo("TrainCapsule product tools are ready; no network is required.")


@case_app.command("init")
def case_init(
    case_id: Annotated[str, typer.Option("--case-id")],
    decision_owner: Annotated[str, typer.Option("--decision-owner")],
    decision_type: Annotated[str, typer.Option("--decision-type")],
    decision_deadline: Annotated[str, typer.Option("--decision-deadline")],
    incident_summary: Annotated[str, typer.Option("--incident-summary")],
    pack_candidate: Annotated[str, typer.Option("--pack-candidate")],
    privacy_policy: Annotated[str, typer.Option("--privacy-policy")],
    output: Annotated[Path | None, typer.Option("--output")] = None,
    machine: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        incident = IncidentCase(
            case_id=case_id,
            decision_owner=decision_owner,
            decision_type=decision_type,
            decision_deadline=_parse_datetime(decision_deadline),
            incident_summary=incident_summary,
            evidence_refs=[],
            native_findings=[],
            pack_candidate=pack_candidate,
            economics=CaseEconomics(),
            privacy_policy=privacy_policy,
            status="DRAFT",
        )
        _write_result(incident, output=output, machine=machine)
    except (OSError, ValueError, ValidationError) as error:
        _fail(str(error), code=ExitCode.INVALID_INPUT, machine=machine)


def _identity_command(
    *,
    kind: str,
    input_path: Path,
    output: Path | None,
    machine: bool,
) -> None:
    try:
        payload = _read_object(input_path)
        identity = (
            build_workload_identity(payload)
            if kind == "workload"
            else build_environment_identity(payload)
        )
        _write_result(identity, output=output, machine=machine)
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as error:
        _fail(str(error), code=ExitCode.INVALID_INPUT, machine=machine)


@identity_app.command("workload")
def identity_workload(
    input_path: Annotated[Path, typer.Argument(help="Workload identity material JSON.")],
    output: Annotated[Path | None, typer.Option("--output")] = None,
    machine: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _identity_command(
        kind="workload", input_path=input_path, output=output, machine=machine
    )


@identity_app.command("environment")
def identity_environment(
    input_path: Annotated[Path, typer.Argument(help="Environment identity material JSON.")],
    output: Annotated[Path | None, typer.Option("--output")] = None,
    machine: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _identity_command(
        kind="environment", input_path=input_path, output=output, machine=machine
    )


@ingest_app.command("pytorch-flight-recorder")
def ingest_pytorch_flight_recorder(
    trace_dir: Annotated[Path, typer.Argument(help="Local Flight Recorder directory.")],
    case_id: Annotated[str, typer.Option("--case-id")],
    store_root: Annotated[Path, typer.Option("--store")],
    captured_at: Annotated[str, typer.Option("--captured-at")],
    output: Annotated[Path | None, typer.Option("--output")] = None,
    machine: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        imported = PyTorchFlightRecorderImporter().import_trace(
            trace_dir=trace_dir,
            case_id=case_id,
            store=LocalEvidenceStore(store_root),
            captured_at=_parse_datetime(captured_at),
        )
        _write_result(imported, output=output, machine=machine)
    except FlightRecorderImportError as error:
        exit_code = (
            ExitCode.UNSUPPORTED_VERSION
            if error.code is ImportErrorCode.UNSUPPORTED_VERSION
            else ExitCode.POLICY_BLOCKED
            if error.code is ImportErrorCode.POLICY_BLOCKED
            else ExitCode.INVALID_INPUT
        )
        _fail(str(error), code=exit_code, machine=machine, error_code=error.code.value)
    except (EvidenceStoreError, OSError, ValueError) as error:
        _fail(str(error), code=ExitCode.LOCAL_IO_ERROR, machine=machine)


@app.command("native-baseline")
def native_baseline(
    input_path: Annotated[Path, typer.Argument(help="Native baseline JSON.")],
    output: Annotated[Path | None, typer.Option("--output")] = None,
    machine: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        baseline = NativeBaseline.model_validate(_read_object(input_path))
        _write_result(baseline, output=output, machine=machine)
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as error:
        _fail(str(error), code=ExitCode.INVALID_INPUT, machine=machine)


@app.command("preflight")
def preflight(
    input_path: Annotated[Path, typer.Argument(help="Preflight inputs JSON.")],
    output: Annotated[Path | None, typer.Option("--output")] = None,
    machine: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        inputs = PreflightInputs.model_validate(_read_object(input_path))
        _write_result(evaluate_preflight(inputs), output=output, machine=machine)
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as error:
        _fail(str(error), code=ExitCode.INVALID_INPUT, machine=machine)


if __name__ == "__main__":
    app()
