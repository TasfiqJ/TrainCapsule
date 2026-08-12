from __future__ import annotations

import json
import os
import sys
import threading
from contextlib import suppress
from pathlib import Path

import pytest
from traincapsule_cli.cli import ExitCode, app, main, write_payloads_exclusive
from traincapsule_core.evidence import LocalEvidenceStore
from traincapsule_core.models import EligibilityOutcome
from traincapsule_qualify import PreflightInputs
from typer.testing import CliRunner

from .test_identity import workload_material
from .test_qualification import (
    BASELINE_RECIPE,
    CANDIDATE_RECIPE,
    PAYLOADS,
    make_inputs,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "examples/product/flight-recorder"
runner = CliRunner()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def binding_args(tmp_path: Path) -> list[str]:
    inputs = make_inputs()
    baseline = tmp_path / "baseline.recipe"
    candidate = tmp_path / "candidate.recipe"
    baseline.write_bytes(BASELINE_RECIPE)
    candidate.write_bytes(CANDIDATE_RECIPE)
    return [
        "--workload-id", inputs.workload_identity.workload_id,
        "--baseline-environment-id", inputs.baseline_environment.environment_id,
        "--candidate-environment-id", inputs.candidate_environment.environment_id,
        "--baseline-recipe", str(baseline),
        "--candidate-recipe", str(candidate),
    ]


def test_doctor_is_offline_and_machine_readable() -> None:
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == ExitCode.OK
    payload = json.loads(result.stdout)
    assert payload["checks"]["networkRequired"] is False


def test_workload_identity_command_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "workload.json"
    write_json(source, workload_material())
    first = runner.invoke(app, ["identity", "workload", str(source), "--json"])
    second = runner.invoke(app, ["identity", "workload", str(source), "--json"])
    assert first.exit_code == second.exit_code == ExitCode.OK
    assert first.stdout == second.stdout


def test_deep_control_json_has_deterministic_machine_error(tmp_path: Path) -> None:
    source = tmp_path / "deep.json"
    source.write_bytes(b'{"nested":' + b"[" * 65 + b"0" + b"]" * 65 + b"}")
    first = runner.invoke(app, ["identity", "workload", str(source), "--json"])
    second = runner.invoke(app, ["identity", "workload", str(source), "--json"])
    assert first.exit_code == second.exit_code == ExitCode.INVALID_INPUT
    assert first.stderr == second.stderr
    assert json.loads(first.stderr) == {
        "code": "INVALID_INPUT",
        "message": "input exceeds the JSON nesting limit",
        "ok": False,
    }


def test_output_parent_symlink_swap_cannot_escape_selected_directory(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    parked = tmp_path / "parked"
    outside = tmp_path / "outside"
    output_root.mkdir()
    outside.mkdir()
    stop = threading.Event()

    def swap_parent() -> None:
        while not stop.is_set():
            try:
                os.rename(output_root, parked)
                os.symlink(outside, output_root, target_is_directory=True)
                os.unlink(output_root)
                os.rename(parked, output_root)
            except OSError:
                continue

    worker = threading.Thread(target=swap_parent, daemon=True)
    worker.start()
    try:
        for attempt in range(200):
            name = f"result-{attempt}.json"
            with suppress(OSError, ValueError):
                write_payloads_exclusive({output_root / name: b"{}"})
        assert list(outside.iterdir()) == []
    finally:
        stop.set()
        worker.join(timeout=2)
        if output_root.is_symlink():
            output_root.unlink()
        if parked.exists() and not output_root.exists():
            os.rename(parked, output_root)


def test_ingest_exact_unsupported_and_policy_exit_codes(tmp_path: Path) -> None:
    supported = runner.invoke(
        app,
        [
            "ingest",
            "pytorch-flight-recorder",
            str(FIXTURES / "real-format"),
            "--case-id",
            "CASE-CLI",
            "--store",
            str(tmp_path / "store"),
            "--captured-at",
            "2026-08-11T20:00:00Z",
            *binding_args(tmp_path),
            "--json",
        ],
    )
    assert supported.exit_code == ExitCode.OK
    unsupported = runner.invoke(
        app,
        [
            "ingest",
            "pytorch-flight-recorder",
            str(FIXTURES / "unsupported"),
            "--case-id",
            "CASE-UNSUPPORTED",
            "--store",
            str(tmp_path / "bad-store"),
            "--captured-at",
            "2026-08-11T20:00:00Z",
            *binding_args(tmp_path),
            "--json",
        ],
    )
    assert unsupported.exit_code == ExitCode.UNSUPPORTED_VERSION
    assert json.loads(unsupported.stderr)["code"] == "UNSUPPORTED_VERSION"
    trace = tmp_path / "malicious"
    trace.mkdir()
    (trace / "rank.json").symlink_to(FIXTURES / "real-format/rank-0.json")
    blocked = runner.invoke(
        app,
        [
            "ingest",
            "pytorch-flight-recorder",
            str(trace),
            "--case-id",
            "CASE-BLOCK",
            "--store",
            str(tmp_path / "blocked-store"),
            "--captured-at",
            "2026-08-11T20:00:00Z",
            *binding_args(tmp_path),
            "--json",
        ],
    )
    assert blocked.exit_code == ExitCode.POLICY_BLOCKED


def test_native_baseline_generates_machine_and_human_records(tmp_path: Path) -> None:
    imported = tmp_path / "import.json"
    ingest = runner.invoke(
        app,
        [
            "ingest",
            "pytorch-flight-recorder",
            str(FIXTURES / "real-format"),
            "--case-id",
            "CASE-NATIVE",
            "--store",
            str(tmp_path / "store"),
            "--captured-at",
            "2026-08-11T20:00:00Z",
            *binding_args(tmp_path),
            "--output",
            str(imported),
            "--json",
        ],
    )
    assert ingest.exit_code == ExitCode.OK
    machine = tmp_path / "native.json"
    human = tmp_path / "native.md"
    generated = runner.invoke(
        app,
        [
            "native-baseline",
            str(imported),
            "--store",
            str(tmp_path / "store"),
            "--executed-at",
            "2026-08-11T20:01:00Z",
            "--elapsed-seconds",
            "60",
            "--operator-effort-seconds",
            "0",
            "--unresolved-question",
            "Whether to approve the candidate.",
            "--output",
            str(machine),
            "--human-output",
            str(human),
            "--json",
        ],
    )
    assert generated.exit_code == ExitCode.OK, generated.output
    payload = json.loads(machine.read_bytes())
    assert payload["operatorEffortSeconds"] == 0
    assert payload["findings"][0]["attribution"] == "NATIVE_TOOL_FOUND"
    report = human.read_text(encoding="utf-8")
    assert "### NATIVE_TOOL_FOUND" in report
    assert "### UNKNOWN" in report
    assert "Configuration:" in report


def test_native_decision_is_not_a_caller_option_and_paired_outputs_fail_atomically(
    tmp_path: Path,
) -> None:
    help_result = runner.invoke(app, ["native-baseline", "--help"])
    assert "--decision-reached" not in help_result.stdout
    rejected = runner.invoke(app, ["native-baseline", "missing.json", "--decision-reached", "yes"])
    assert rejected.exit_code == ExitCode.INVALID_INPUT

    imported = tmp_path / "import.json"
    ingest = runner.invoke(
        app,
        [
            "ingest",
            "pytorch-flight-recorder",
            str(FIXTURES / "real-format"),
            "--case-id",
            "CASE-ATOMIC",
            "--store",
            str(tmp_path / "store"),
            "--captured-at",
            "2026-08-11T20:00:00Z",
            *binding_args(tmp_path),
            "--output",
            str(imported),
            "--json",
        ],
    )
    assert ingest.exit_code == ExitCode.OK
    machine = tmp_path / "native.json"
    human = tmp_path / "native.md"
    human.write_text("existing", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "native-baseline",
            str(imported),
            "--store",
            str(tmp_path / "store"),
            "--executed-at",
            "2026-08-11T20:01:00Z",
            "--elapsed-seconds",
            "1",
            "--operator-effort-seconds",
            "0",
            "--output",
            str(machine),
            "--human-output",
            str(human),
            "--json",
        ],
    )
    assert result.exit_code == ExitCode.INVALID_INPUT
    assert not machine.exists()
    assert human.read_text(encoding="utf-8") == "existing"


def test_native_baseline_rejects_caller_edited_import_entries(tmp_path: Path) -> None:
    store = tmp_path / "store"
    imported = tmp_path / "import.json"
    ingest = runner.invoke(
        app,
        [
            "ingest",
            "pytorch-flight-recorder",
            str(FIXTURES / "real-format"),
            "--case-id",
            "CASE-EDITED",
            "--store",
            str(store),
            "--captured-at",
            "2026-08-11T20:00:00Z",
            *binding_args(tmp_path),
            "--output",
            str(imported),
            "--json",
        ],
    )
    assert ingest.exit_code == ExitCode.OK
    value = json.loads(imported.read_bytes())
    value["entries"][1]["state"] = "completed"
    imported.write_text(json.dumps(value), encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "native-baseline",
            str(imported),
            "--store",
            str(store),
            "--executed-at",
            "2026-08-11T20:01:00Z",
            "--elapsed-seconds",
            "1",
            "--operator-effort-seconds",
            "0",
            "--output",
            str(tmp_path / "native.json"),
            "--json",
        ],
    )
    assert result.exit_code == ExitCode.INVALID_INPUT
    assert "do not match raw CAS evidence" in result.stderr


def test_preflight_validates_bound_record(tmp_path: Path) -> None:
    inputs = make_inputs()
    store_root = tmp_path / "evidence"
    store = LocalEvidenceStore(store_root)
    for expected in inputs.verified_artifacts:
        stored = store.put_bytes(
            case_id=expected.case_id,
            payload=PAYLOADS[expected.content_digest],
            kind=expected.kind,
            source_adapter=expected.source_adapter,
            source_version=expected.source_version,
            captured_at=expected.captured_at,
            privacy_class=expected.privacy_class,
            provenance=expected.provenance,
            workload_id=expected.workload_id,
            baseline_environment_id=expected.baseline_environment_id,
            candidate_environment_id=expected.candidate_environment_id,
        )
        assert stored == expected
    source = tmp_path / "preflight.json"
    write_json(source, inputs.model_dump(mode="json", by_alias=True))
    result = runner.invoke(app, ["preflight", str(source), "--store", str(store_root), "--json"])
    assert result.exit_code == ExitCode.QUALIFICATION_PASS
    assert json.loads(result.stdout)["outcome"] == EligibilityOutcome.ELIGIBLE_FOR_QUALIFICATION
    invalid = PreflightInputs.model_validate(inputs.model_dump())
    assert invalid.incident_case.case_id == "CASE-QUALIFY"


def test_installed_entry_parser_errors_are_json_when_requested(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["traincapsule", "case", "init", "--json"])
    with pytest.raises(SystemExit) as raised:
        main()
    assert raised.value.code == ExitCode.INVALID_INPUT
    payload = json.loads(capfd.readouterr().err)
    assert payload["code"] == "INVALID_INPUT" and payload["ok"] is False


def test_required_command_tree_is_exposed() -> None:
    for arguments in (
        ["doctor", "--help"],
        ["case", "init", "--help"],
        ["ingest", "pytorch-flight-recorder", "--help"],
        ["identity", "workload", "--help"],
        ["identity", "environment", "--help"],
        ["native-baseline", "--help"],
        ["preflight", "--help"],
    ):
        assert runner.invoke(app, arguments).exit_code == 0
