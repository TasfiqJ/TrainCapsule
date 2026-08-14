"""Bounded, shell-free customer-local baseline and candidate qualification."""

from __future__ import annotations

import base64
import os
import selectors
import signal
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from traincapsule_core.base import canonical_json_bytes, digest_json
from traincapsule_core.evidence import LocalEvidenceStore
from traincapsule_core.models import EligibilityOutcome

from .models import (
    CommandExpectation,
    ExperimentRun,
    ExperimentSpecification,
    PreflightInputs,
    QualificationDecision,
    QualificationResult,
)
from .qualify import evaluate_preflight


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        process.kill()


def _read_bounded_process(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout_seconds: int,
    max_output_bytes: int,
) -> tuple[int | None, bytes, bytes, bool, bool, datetime, datetime, int]:
    started_at = datetime.now(UTC)
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        start_new_session=True,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    timed_out = False
    output_limit_exceeded = False
    try:
        while selector.get_map():
            remaining = timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                timed_out = True
                _kill_process_group(process)
                remaining = 0.1
            events = selector.select(timeout=min(max(remaining, 0.01), 0.1))
            if not events and process.poll() is not None:
                events = [(key, selectors.EVENT_READ) for key in selector.get_map().values()]
            for key, _ in events:
                chunk = os.read(key.fd, 65_536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                total = len(buffers["stdout"]) + len(buffers["stderr"])
                available = max_output_bytes - total
                if available > 0:
                    buffers[key.data].extend(chunk[:available])
                if len(chunk) > available:
                    output_limit_exceeded = True
                    _kill_process_group(process)
        process.wait()
    finally:
        selector.close()
        if process.poll() is None:
            _kill_process_group(process)
            process.wait()
    finished_at = datetime.now(UTC)
    elapsed = max(0, round((time.monotonic() - started) * 1000))
    return (
        process.returncode,
        bytes(buffers["stdout"]),
        bytes(buffers["stderr"]),
        timed_out,
        output_limit_exceeded,
        started_at,
        finished_at,
        elapsed,
    )


def _expectation_met(
    expectation: CommandExpectation, *, exit_code: int | None, stdout: bytes, stderr: bytes
) -> bool:
    combined = stdout + b"\n" + stderr
    return (
        exit_code in expectation.expected_exit_codes
        and all(token.encode("utf-8") in stdout for token in expectation.required_stdout_tokens)
        and all(
            token.encode("utf-8") not in combined
            for token in expectation.forbidden_output_tokens
        )
    )


def _validate_local_execution(specification: ExperimentSpecification) -> Path:
    requested = Path(specification.working_directory)
    if not requested.is_absolute():
        raise ValueError("experiment workingDirectory must be absolute")
    resolved = requested.resolve(strict=True)
    if resolved != requested.absolute() or not resolved.is_dir():
        raise ValueError("experiment workingDirectory must be a non-symlink directory")
    for command in (specification.baseline_command, specification.candidate_command):
        executable = Path(command[0])
        if executable.resolve(strict=True) != executable or not executable.is_file():
            raise ValueError("experiment executable must be a non-symlink regular file")
        if not os.access(executable, os.X_OK):
            raise ValueError("experiment executable is not locally executable")
    return resolved


def _execute_phase(
    *,
    phase: Literal["baseline", "candidate"],
    command: list[str],
    expectation: CommandExpectation,
    specification: ExperimentSpecification,
    working_directory: Path,
    store: LocalEvidenceStore,
    captured_at: datetime,
) -> ExperimentRun:
    environment = dict(os.environ)
    environment.update(specification.environment)
    values = _read_bounded_process(
        command,
        cwd=working_directory,
        environment=environment,
        timeout_seconds=specification.timeout_seconds,
        max_output_bytes=specification.max_output_bytes,
    )
    exit_code, stdout, stderr, timed_out, limited, started_at, finished_at, elapsed = values
    provenance = {
        "phase": phase,
        "experimentSpecificationDigest": digest_json(
            specification.model_dump(mode="json", by_alias=True)
        ),
    }
    def capture_payload(stream: str, payload: bytes) -> bytes:
        return canonical_json_bytes(
            {
                "encoding": "base64",
                "payload": base64.b64encode(payload).decode("ascii"),
                "phase": phase,
                "stream": stream,
            }
        )

    stdout_artifact = store.put_bytes(
        payload=capture_payload("stdout", stdout),
        kind="qualification-command-stdout",
        source_adapter="traincapsule-local-runner",
        source_version="1",
        captured_at=captured_at,
        provenance=provenance,
        case_id=specification.case_id,
        workload_id=specification.workload_id,
        baseline_environment_id=specification.baseline_environment_id,
        candidate_environment_id=specification.candidate_environment_id,
    )
    stderr_artifact = store.put_bytes(
        payload=capture_payload("stderr", stderr),
        kind="qualification-command-stderr",
        source_adapter="traincapsule-local-runner",
        source_version="1",
        captured_at=captured_at,
        provenance=provenance,
        case_id=specification.case_id,
        workload_id=specification.workload_id,
        baseline_environment_id=specification.baseline_environment_id,
        candidate_environment_id=specification.candidate_environment_id,
    )
    return ExperimentRun(
        phase=phase,
        command_digest=digest_json(command),
        stdout_artifact=stdout_artifact,
        stderr_artifact=stderr_artifact,
        exit_code=exit_code,
        timed_out=timed_out,
        output_limit_exceeded=limited,
        expectation_met=(
            not timed_out
            and not limited
            and _expectation_met(expectation, exit_code=exit_code, stdout=stdout, stderr=stderr)
        ),
        started_at=started_at,
        finished_at=finished_at,
        elapsed_milliseconds=elapsed,
    )


def execute_qualification(
    inputs: PreflightInputs,
    specification: ExperimentSpecification,
    *,
    store: LocalEvidenceStore,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> QualificationDecision:
    """Run the complete baseline/candidate experiment only after evidence preflight passes."""
    generated_at = now()
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("qualification clock must return a timezone-aware timestamp")
    eligibility = evaluate_preflight(
        inputs,
        artifact_reader=lambda artifact: store.get_bytes(
            case_id=inputs.incident_case.case_id, artifact=artifact
        ),
    )
    spec_digest = digest_json(specification.model_dump(mode="json", by_alias=True))
    eligibility_digest = digest_json(eligibility.model_dump(mode="json", by_alias=True))
    evidence_refs = sorted(artifact.artifact_id for artifact in inputs.verified_artifacts)
    expected_binding = (
        inputs.incident_case.case_id,
        inputs.workload_identity.workload_id,
        inputs.baseline_environment.environment_id,
        inputs.candidate_environment.environment_id,
    )
    actual_binding = (
        specification.case_id,
        specification.workload_id,
        specification.baseline_environment_id,
        specification.candidate_environment_id,
    )
    if actual_binding != expected_binding:
        raise ValueError("experiment specification does not match the preflight case identities")
    if generated_at > inputs.incident_case.decision_deadline:
        return QualificationDecision(
            case_id=specification.case_id,
            experiment_specification_digest=spec_digest,
            eligibility_decision_digest=eligibility_digest,
            result=QualificationResult.EXPIRED,
            evidence_refs=evidence_refs,
            reasons=["The named customer decision deadline passed before execution."],
            generated_at=generated_at,
        )
    if eligibility.outcome is not EligibilityOutcome.ELIGIBLE_FOR_QUALIFICATION:
        return QualificationDecision(
            case_id=specification.case_id,
            experiment_specification_digest=spec_digest,
            eligibility_decision_digest=eligibility_digest,
            result=QualificationResult.INAPPLICABLE,
            evidence_refs=evidence_refs,
            reasons=["Evidence preflight did not authorize a candidate experiment."],
            generated_at=generated_at,
        )
    working_directory = _validate_local_execution(specification)
    baseline = _execute_phase(
        phase="baseline",
        command=specification.baseline_command,
        expectation=specification.baseline_expectation,
        specification=specification,
        working_directory=working_directory,
        store=store,
        captured_at=generated_at,
    )
    if baseline.timed_out or baseline.output_limit_exceeded or not baseline.expectation_met:
        result = QualificationResult.UNKNOWN
        reasons = ["The baseline did not faithfully reproduce the specified observation."]
        candidate = None
    else:
        candidate = _execute_phase(
            phase="candidate",
            command=specification.candidate_command,
            expectation=specification.candidate_expectation,
            specification=specification,
            working_directory=working_directory,
            store=store,
            captured_at=generated_at,
        )
        if candidate.timed_out or candidate.output_limit_exceeded:
            result = QualificationResult.UNKNOWN
            reasons = ["The candidate exceeded an explicit experiment budget."]
        elif candidate.expectation_met:
            result = QualificationResult.PASS
            reasons = ["The faithful baseline reproduced and the candidate met the bound oracle."]
        else:
            result = QualificationResult.FAIL
            reasons = [
                "The faithful baseline reproduced but the candidate did not meet the oracle."
            ]
    run_refs = [baseline.stdout_artifact.artifact_id, baseline.stderr_artifact.artifact_id]
    if candidate is not None:
        run_refs.extend(
            [candidate.stdout_artifact.artifact_id, candidate.stderr_artifact.artifact_id]
        )
    return QualificationDecision(
        case_id=specification.case_id,
        experiment_specification_digest=spec_digest,
        eligibility_decision_digest=eligibility_digest,
        result=result,
        baseline_run=baseline,
        candidate_run=candidate,
        evidence_refs=sorted(set(evidence_refs + run_refs)),
        reasons=reasons,
        generated_at=generated_at,
    )
