from __future__ import annotations

import json
from pathlib import Path

from traincapsule_cli.cli import ExitCode, app
from typer.testing import CliRunner

from .test_identity import environment_material, workload_material
from .test_qualification import make_inputs, native_baseline

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "examples/product/flight-recorder"
runner = CliRunner()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_doctor_is_offline_and_machine_readable() -> None:
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == ExitCode.OK
    assert json.loads(result.stdout) == {
        "checks": {
            "networkRequired": False,
            "productPackages": "available",
            "python": "3.12",
        },
        "ok": True,
        "productSchemaVersion": 1,
    }


def test_workload_identity_command_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "workload.json"
    write_json(source, workload_material())
    first = runner.invoke(app, ["identity", "workload", str(source), "--json"])
    second = runner.invoke(app, ["identity", "workload", str(source), "--json"])
    assert first.exit_code == second.exit_code == ExitCode.OK
    assert first.stdout == second.stdout
    assert json.loads(first.stdout)["workloadId"].startswith("sha256:")

    environment_source = tmp_path / "environment.json"
    write_json(environment_source, environment_material())
    environment = runner.invoke(
        app, ["identity", "environment", str(environment_source), "--json"]
    )
    assert environment.exit_code == ExitCode.OK
    assert json.loads(environment.stdout)["environmentId"].startswith("sha256:")


def test_case_init_has_no_hidden_timestamp_and_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "case.json"
    arguments = [
        "case",
        "init",
        "--case-id",
        "CASE-CLI",
        "--decision-owner",
        "incident-owner",
        "--decision-type",
        "candidate approval",
        "--decision-deadline",
        "2026-08-12T20:00:00Z",
        "--incident-summary",
        "collective timeout",
        "--pack-candidate",
        "ddp-hang-v1",
        "--privacy-policy",
        "LOCAL_ONLY",
        "--output",
        str(output),
        "--json",
    ]
    created = runner.invoke(app, arguments)
    assert created.exit_code == ExitCode.OK
    payload = json.loads(output.read_bytes())
    assert payload["caseId"] == "CASE-CLI"
    assert "createdAt" not in payload
    repeated = runner.invoke(app, arguments)
    assert repeated.exit_code == ExitCode.LOCAL_IO_ERROR
    assert json.loads(repeated.stderr)["code"] == "LOCAL_IO_ERROR"


def test_ingest_command_returns_supported_result_and_exact_unsupported_exit(
    tmp_path: Path,
) -> None:
    supported = runner.invoke(
        app,
        [
            "ingest",
            "pytorch-flight-recorder",
            str(FIXTURES / "supported"),
            "--case-id",
            "CASE-CLI-SUPPORTED",
            "--store",
            str(tmp_path / "supported-store"),
            "--captured-at",
            "2026-08-11T20:00:00Z",
            "--json",
        ],
    )
    assert supported.exit_code == ExitCode.OK
    assert json.loads(supported.stdout)["sourceFormatVersion"] == "1.0"

    unsupported = runner.invoke(
        app,
        [
            "ingest",
            "pytorch-flight-recorder",
            str(FIXTURES / "unsupported"),
            "--case-id",
            "CASE-CLI-UNSUPPORTED",
            "--store",
            str(tmp_path / "unsupported-store"),
            "--captured-at",
            "2026-08-11T20:00:00Z",
            "--json",
        ],
    )
    assert unsupported.exit_code == ExitCode.UNSUPPORTED_VERSION
    assert json.loads(unsupported.stderr)["code"] == "UNSUPPORTED_VERSION"


def test_malicious_symlink_has_policy_exit_code(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    trace.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    (trace / "metadata.json").symlink_to(outside)
    result = runner.invoke(
        app,
        [
            "ingest",
            "pytorch-flight-recorder",
            str(trace),
            "--case-id",
            "CASE-CLI-MALICIOUS",
            "--store",
            str(tmp_path / "store"),
            "--captured-at",
            "2026-08-11T20:00:00Z",
            "--json",
        ],
    )
    assert result.exit_code == ExitCode.POLICY_BLOCKED
    assert json.loads(result.stderr)["code"] == "POLICY_BLOCKED"


def test_required_command_tree_is_exposed() -> None:
    root_help = runner.invoke(app, ["--help"])
    assert root_help.exit_code == ExitCode.OK
    for command in ("doctor", "case", "ingest", "identity", "native-baseline", "preflight"):
        assert command in root_help.stdout
    assert "pytorch-flight-recorder" in runner.invoke(app, ["ingest", "--help"]).stdout
    identity_help = runner.invoke(app, ["identity", "--help"]).stdout
    assert "workload" in identity_help
    assert "environment" in identity_help


def test_native_baseline_and_preflight_commands_validate_strict_records(
    tmp_path: Path,
) -> None:
    baseline_path = tmp_path / "native-baseline.json"
    write_json(
        baseline_path,
        native_baseline().model_dump(mode="json", by_alias=True, exclude_none=False),
    )
    baseline_result = runner.invoke(
        app, ["native-baseline", str(baseline_path), "--json"]
    )
    assert baseline_result.exit_code == ExitCode.OK
    assert json.loads(baseline_result.stdout)["toolName"] == "PyTorch Flight Recorder"

    preflight_path = tmp_path / "preflight.json"
    write_json(
        preflight_path,
        make_inputs().model_dump(mode="json", by_alias=True, exclude_none=False),
    )
    preflight_result = runner.invoke(app, ["preflight", str(preflight_path), "--json"])
    assert preflight_result.exit_code == ExitCode.OK
    decision = json.loads(preflight_result.stdout)
    assert decision["outcome"] == "ELIGIBLE_FOR_QUALIFICATION"
    assert decision["operationalDecision"] == "APPROVE_WITHIN_ENVELOPE"
