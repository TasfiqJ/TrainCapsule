"""Offline-first TrainCapsule product CLI."""

from __future__ import annotations

import json
import os
import stat
import sys
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
from traincapsule_core.secure_fs import open_directory_fd
from traincapsule_ingest_pytorch import (
    FlightRecorderImport,
    FlightRecorderImportError,
    ImportErrorCode,
    PyTorchFlightRecorderImporter,
)
from traincapsule_qualify import (
    PreflightInputs,
    evaluate_preflight,
    generate_native_baseline,
    render_native_baseline_human,
)
from typer._click.exceptions import ClickException

app = typer.Typer(no_args_is_help=True, help="Customer-local TrainCapsule product tools.")
case_app = typer.Typer(no_args_is_help=True, help="Create and inspect incident cases.")
ingest_app = typer.Typer(no_args_is_help=True, help="Import customer-local evidence.")
identity_app = typer.Typer(no_args_is_help=True, help="Build deterministic identities.")
app.add_typer(case_app, name="case")
app.add_typer(ingest_app, name="ingest")
app.add_typer(identity_app, name="identity")

_MAX_CONTROL_FILE_BYTES = 4 * 1024 * 1024
_MAX_JSON_DEPTH = 64


class ExitCode(IntEnum):
    OK = 0
    INVALID_INPUT = 2
    UNSUPPORTED_VERSION = 10
    EVIDENCE_INCOMPLETE = 11
    IDENTITY_MISMATCH = 12
    POLICY_BLOCKED = 13
    QUALIFICATION_PASS = 20
    QUALIFICATION_FAIL = 21
    QUALIFICATION_UNKNOWN = 22
    INVALID_ORACLE = 23
    EXPIRED = 24
    LOCAL_IO_ERROR = 30
    SECURITY_VIOLATION = 40


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("timestamp must be ISO 8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include an explicit UTC offset")
    return parsed


def _read_object(path: Path) -> dict[str, object]:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as error:
        raise ValueError("input must be an available non-symlink regular file") from error
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise ValueError("input must be a regular file")
        if details.st_size > _MAX_CONTROL_FILE_BYTES:
            raise ValueError("input exceeds the local control-file limit")
        payload = bytearray()
        while True:
            chunk = os.read(
                descriptor,
                min(1024 * 1024, _MAX_CONTROL_FILE_BYTES + 1 - len(payload)),
            )
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > _MAX_CONTROL_FILE_BYTES:
                raise ValueError("input exceeds the local control-file limit")
    finally:
        os.close(descriptor)
    depth = 0
    in_string = False
    escaped = False
    for value in payload:
        if in_string:
            if escaped:
                escaped = False
            elif value == 0x5C:
                escaped = True
            elif value == 0x22:
                in_string = False
            continue
        if value == 0x22:
            in_string = True
        elif value in (0x5B, 0x7B):
            depth += 1
            if depth > _MAX_JSON_DEPTH:
                raise ValueError("input exceeds the JSON nesting limit")
        elif value in (0x5D, 0x7D):
            depth -= 1
    try:
        raw: object = json.loads(bytes(payload))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("input must be valid bounded UTF-8 JSON") from error
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
    rendered = _render_result(value)
    if output is None:
        typer.echo(rendered.decode("utf-8"), nl=False)
        return
    try:
        write_payloads_exclusive({output: rendered})
    except (OSError, ValueError) as error:
        _fail(str(error), code=ExitCode.LOCAL_IO_ERROR, machine=machine)
    if machine:
        typer.echo(
            _machine_message(ok=True, code="OK", message=str(output.resolve())).decode("utf-8"),
            nl=False,
        )
    else:
        typer.echo(f"Wrote {output.resolve()}")


def _render_result(value: BaseModel | dict[str, object]) -> bytes:
    payload: object = (
        value.model_dump(mode="json", by_alias=True, exclude_none=False)
        if isinstance(value, BaseModel)
        else value
    )
    return canonical_json_bytes(payload)


def write_payloads_exclusive(payloads: dict[Path, bytes]) -> None:
    if len({path.absolute() for path in payloads}) != len(payloads):
        raise ValueError("output paths must be distinct")
    descriptors: dict[Path, int] = {}
    parents: dict[Path, int] = {}
    created: list[Path] = []
    try:
        for path in payloads:
            parent_descriptor = open_directory_fd(path.parent, create=True)
            parents[path] = parent_descriptor
            descriptor = os.open(
                path.name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=parent_descriptor,
            )
            descriptors[path] = descriptor
            created.append(path)
        for path, payload in payloads.items():
            with os.fdopen(descriptors.pop(path), "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.fsync(parents[path])
    except Exception:
        for descriptor in descriptors.values():
            os.close(descriptor)
        for path in created:
            try:
                os.unlink(path.name, dir_fd=parents[path])
                os.fsync(parents[path])
            except FileNotFoundError:
                pass
        raise
    finally:
        for descriptor in parents.values():
            os.close(descriptor)


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
    _identity_command(kind="workload", input_path=input_path, output=output, machine=machine)


@identity_app.command("environment")
def identity_environment(
    input_path: Annotated[Path, typer.Argument(help="Environment identity material JSON.")],
    output: Annotated[Path | None, typer.Option("--output")] = None,
    machine: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _identity_command(kind="environment", input_path=input_path, output=output, machine=machine)


@ingest_app.command("pytorch-flight-recorder")
def ingest_pytorch_flight_recorder(
    trace_dir: Annotated[Path, typer.Argument(help="Local Flight Recorder directory.")],
    case_id: Annotated[str, typer.Option("--case-id")],
    store_root: Annotated[Path, typer.Option("--store")],
    captured_at: Annotated[str, typer.Option("--captured-at")],
    workload_id: Annotated[str, typer.Option("--workload-id")],
    baseline_environment_id: Annotated[str, typer.Option("--baseline-environment-id")],
    candidate_environment_id: Annotated[str, typer.Option("--candidate-environment-id")],
    baseline_recipe: Annotated[Path, typer.Option("--baseline-recipe")],
    candidate_recipe: Annotated[Path, typer.Option("--candidate-recipe")],
    output: Annotated[Path | None, typer.Option("--output")] = None,
    machine: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        captured = _parse_datetime(captured_at)
        store = LocalEvidenceStore(store_root)
        imported = PyTorchFlightRecorderImporter().import_trace(
            trace_dir=trace_dir,
            case_id=case_id,
            store=store,
            captured_at=captured,
            workload_id=workload_id,
            baseline_environment_id=baseline_environment_id,
            candidate_environment_id=candidate_environment_id,
        )
        binding_artifacts = [
            store.put_file(
                source=path,
                case_id=case_id,
                kind=kind,
                source_adapter="traincapsule-materialization-recipe",
                source_version="1",
                captured_at=captured,
                workload_id=workload_id,
                baseline_environment_id=baseline_environment_id,
                candidate_environment_id=candidate_environment_id,
            )
            for path, kind in (
                (baseline_recipe, "BASELINE_MATERIALIZATION_RECIPE"),
                (candidate_recipe, "CANDIDATE_MATERIALIZATION_RECIPE"),
            )
        ]
        imported = imported.model_copy(update={"binding_artifacts": binding_artifacts})
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
    input_path: Annotated[Path, typer.Argument(help="Flight Recorder import JSON.")],
    store_root: Annotated[Path, typer.Option("--store")],
    executed_at: Annotated[str, typer.Option("--executed-at")],
    elapsed_seconds: Annotated[int, typer.Option("--elapsed-seconds", min=0)],
    operator_effort_seconds: Annotated[int, typer.Option("--operator-effort-seconds", min=0)],
    unresolved_question: Annotated[list[str] | None, typer.Option("--unresolved-question")] = None,
    output: Annotated[Path | None, typer.Option("--output")] = None,
    human_output: Annotated[Path | None, typer.Option("--human-output")] = None,
    machine: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        imported = FlightRecorderImport.model_validate(_read_object(input_path))
        store = LocalEvidenceStore(store_root)
        baseline = generate_native_baseline(
            imported=imported,
            command=["traincapsule", "ingest", "pytorch-flight-recorder"],
            configuration={"source": "customer-local"},
            elapsed_seconds=elapsed_seconds,
            operator_effort_seconds=operator_effort_seconds,
            unresolved_questions=unresolved_question or [],
            executed_at=_parse_datetime(executed_at),
            artifact_reader=lambda artifact: store.get_bytes(
                case_id=imported.case_id, artifact=artifact
            ),
        )
        report = render_native_baseline_human(baseline)
        report_path = human_output or (output.with_suffix(".md") if output else None)
        if report_path is not None and output is not None:
            write_payloads_exclusive(
                {output: _render_result(baseline), report_path: report.encode("utf-8")}
            )
            if machine:
                typer.echo(
                    _machine_message(ok=True, code="OK", message=str(output.resolve())).decode(
                        "utf-8"
                    ),
                    nl=False,
                )
            else:
                typer.echo(f"Wrote {output.resolve()} and {report_path.resolve()}")
            return
        if report_path is not None:
            write_payloads_exclusive({report_path: report.encode("utf-8")})
        if output is None and not machine:
            typer.echo(report, nl=False)
            return
        _write_result(baseline, output=output, machine=machine)
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as error:
        _fail(str(error), code=ExitCode.INVALID_INPUT, machine=machine)


@app.command("preflight")
def preflight(
    input_path: Annotated[Path, typer.Argument(help="Preflight inputs JSON.")],
    store_root: Annotated[Path, typer.Option("--store")],
    output: Annotated[Path | None, typer.Option("--output")] = None,
    machine: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        inputs = PreflightInputs.model_validate(_read_object(input_path))
        store = LocalEvidenceStore(store_root)
        decision = evaluate_preflight(
            inputs,
            artifact_reader=lambda artifact: store.get_bytes(
                case_id=inputs.incident_case.case_id,
                artifact=artifact,
            ),
        )
        _write_result(decision, output=output, machine=machine)
        codes = {
            "ELIGIBLE_FOR_QUALIFICATION": ExitCode.QUALIFICATION_PASS,
            "NATIVE_WORKFLOW_SUFFICIENT": ExitCode.QUALIFICATION_PASS,
            "NEEDS_MORE_EVIDENCE": ExitCode.EVIDENCE_INCOMPLETE,
            "POLICY_BLOCKED": ExitCode.POLICY_BLOCKED,
            "OUTSIDE_SUPPORTED_ENVELOPE": ExitCode.UNSUPPORTED_VERSION,
            "TECHNICALLY_POSSIBLE_BUT_UNECONOMIC": ExitCode.QUALIFICATION_FAIL,
            "UNKNOWN": (
                ExitCode.EXPIRED
                if decision.technical_result.value == "EXPIRED"
                else ExitCode.QUALIFICATION_UNKNOWN
            ),
        }
        raise typer.Exit(codes[decision.outcome.value])
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as error:
        _fail(str(error), code=ExitCode.INVALID_INPUT, machine=machine)


def main() -> None:
    """Console entry with JSON-form parser failures when --json was requested."""
    machine = "--json" in sys.argv[1:]
    try:
        result = app(standalone_mode=False)
        if isinstance(result, int) and result != 0:
            raise SystemExit(result)
    except typer.Exit as error:
        raise SystemExit(error.exit_code) from error
    except ClickException as error:
        if machine:
            sys.stderr.buffer.write(
                _machine_message(ok=False, code="INVALID_INPUT", message=error.format_message())
            )
        else:
            error.show()
        raise SystemExit(ExitCode.INVALID_INPUT) from error


if __name__ == "__main__":
    main()
