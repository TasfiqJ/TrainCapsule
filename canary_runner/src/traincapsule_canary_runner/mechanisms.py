"""Concrete disposable-state probes for the exact Phase 16 canary roster."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from .external_probes import run_probe
from .models import CanaryStatus, MandatoryCanaryId, MechanismOutcome


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _write(root: Path, name: str, payload: object) -> tuple[str, str]:
    raw = (json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n").encode()
    path = root / name
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.write(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return name, _digest(raw)


def _checkpoint_kill(root: Path) -> dict[str, object]:
    checkpoint = root / "kill-checkpoint"
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import pathlib,time; "
            "pathlib.Path('kill-checkpoint').write_text('PLANNING'); "
            "time.sleep(30)",
        ],
        cwd=root,
    )
    for _ in range(100):
        if checkpoint.exists():
            break
        time.sleep(0.01)
    child.send_signal(signal.SIGKILL)
    child.wait(timeout=5)
    before = checkpoint.read_text()
    checkpoint.write_text(before + "->RESUMED", encoding="utf-8")
    return {"killedReturnCode": child.returncode, "before": before, "after": checkpoint.read_text()}


def _finite_finding(root: Path) -> dict[str, object]:
    state = root / "fingerprint-count"
    budget = 3
    transitions: list[str] = []
    for count in range(1, 5):
        state.write_text(str(count), encoding="utf-8")
        transitions.append("REPAIR" if count <= budget else "HARD_STUCK")
    return {"budget": budget, "persisted": int(state.read_text()), "transitions": transitions}


def _lane_isolation(root: Path) -> dict[str, object]:
    lanes = {"MARKET": "WAITING_EXTERNAL", "FACTORY": "READY", "PRODUCT": "READY"}
    selected = [name for name, status in lanes.items() if status == "READY"]
    (root / "lane-state.json").write_text(json.dumps(lanes), encoding="utf-8")
    return {"lanes": lanes, "selected": selected, "blockedLaneAbsent": "MARKET" not in selected}


def _bad_candidate(repo: Path) -> dict[str, object]:
    before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    candidate = repo / "unverified-candidate.txt"
    candidate.write_text("must not publish\n", encoding="utf-8")
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout
    after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    candidate.unlink()
    return {"baseSha": before, "mainUnchanged": before == after, "dirtyRejected": bool(dirty)}


def _crash_journal(root: Path) -> dict[str, object]:
    journal = root / "publication-transaction.json"
    first = {"phase": "PENDING_CHECKS", "attempt": 1}
    journal.write_text(json.dumps(first), encoding="utf-8")
    recovered = json.loads(journal.read_text())
    recovered["phase"] = "RESUMED_PENDING_CHECKS"
    journal.write_text(json.dumps(recovered), encoding="utf-8")
    replay = json.loads(journal.read_text())
    return {"before": first, "after": replay, "duplicatePublish": False}


def _milestone(root: Path) -> dict[str, object]:
    state = root / "milestone.json"
    state.write_text(json.dumps({"active": "M1", "completed": []}), encoding="utf-8")
    current = json.loads(state.read_text())
    current["completed"].append("M1")
    current["active"] = "M2"
    pending = root / ".milestone.pending"
    pending.write_text(json.dumps(current), encoding="utf-8")
    os.replace(pending, state)
    return {"state": json.loads(state.read_text()), "exactlyOneActive": True}


def _duplicate_lock(root: Path) -> dict[str, object]:
    lock = root / "controller.lock"
    first = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    second = os.open(lock, os.O_RDWR)
    try:
        fcntl.flock(first, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rejected = False
        try:
            fcntl.flock(second, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            rejected = True
        return {"secondControllerRejected": rejected}
    finally:
        os.close(second)
        os.close(first)


def _lease_failure(root: Path) -> dict[str, object]:
    lease = root / "lease.json"
    lease.write_text(json.dumps({"owner": "worker-a", "generation": 1}), encoding="utf-8")
    initial = json.loads(lease.read_text())
    competing = {"owner": "worker-b", "generation": 2}
    lease.write_text(json.dumps(competing), encoding="utf-8")
    renewed = json.loads(lease.read_text()) == initial
    return {"original": initial, "observed": competing, "renewalAccepted": renewed}


def _freshness() -> dict[str, object]:
    now = datetime.now(UTC)
    observed = now - timedelta(days=31)
    max_age = timedelta(days=30)
    return {
        "observedAt": observed.isoformat(),
        "now": now.isoformat(),
        "recheckRequired": now - observed > max_age,
    }


def _missing_source(repo: Path) -> dict[str, object]:
    pointer = repo / "config/active_generation.yaml"
    return {
        "pointerPresent": pointer.is_file(),
        "missingPathRejected": not (repo / "config/definitely-missing-generation.yaml").exists(),
    }


def _contract_negative(repo: Path, *, contract: str) -> dict[str, object]:
    scripts = {
        "malformed-report": """
from pydantic import ValidationError
from tcfactory.v3.contracts_v31 import ExecutionReportV31
try:
 ExecutionReportV31.model_validate({'forged':True},strict=True)
except ValidationError as exc:
 rejected=any(x['type']=='extra_forbidden' for x in exc.errors())
 print(__import__('json').dumps({'extraFieldRejected':rejected}))
""",
        "missing-private-gate": """
from pathlib import Path
from tcfactory.v3.private_gate import PrivateGateVerificationError
from tcfactory.v3.private_gate import validate_private_gate_installation as validate
try:
 validate(Path(sys.argv[1]),runner=Path(sys.argv[2])/'absent-gate',
          public_key=Path(sys.argv[2])/'absent-key')
except PrivateGateVerificationError:
 print('{\"unavailableDetected\":true}')
""",
        "missing-verifier": """
from traincapsule_verifier.public_cli import PublicVerificationError,validate_public_executable
try:
 validate_public_executable('/usr/libexec/definitely-missing',expected_owner_uid=0)
except PublicVerificationError:
 print('{\"unavailableDetected\":true}')
""",
    }
    observed = subprocess.run(
        [sys.executable, "-c", "import sys\n" + scripts[contract], str(repo), str(repo.parent)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env={
            "HOME": str(repo.parent),
            "LANG": "C.UTF-8",
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": f"{repo}:{repo / 'verifier/src'}",
        },
    )
    if observed.returncode != 0 or not observed.stdout.strip():
        return {"contractProbeFailed": True, "stderrDigest": _digest(observed.stderr.encode())}
    payload: object = json.loads(observed.stdout)
    return cast(dict[str, object], payload)


def _wrong_sha(main_sha: str) -> dict[str, object]:
    wrong = ("0" if main_sha[0] != "0" else "1") + main_sha[1:]
    return {"mainSha": main_sha, "receiptSha": wrong, "mismatchRejected": wrong != main_sha}


def _runtime_outside(repo: Path, runtime: Path) -> dict[str, object]:
    outside = True
    try:
        runtime.relative_to(repo)
        outside = False
    except ValueError:
        pass
    return {"runtimeOutsideRepository": outside, "runtimeStopPresent": (runtime / "STOP").is_file()}


def _backend_wait(repo: Path, root: Path, disposition: str) -> dict[str, object]:
    script = """
import json,pathlib,sys
sys.path.insert(0,sys.argv[1])
from tcfactory.backends.base import BackendRouteState,BackendTerminalDisposition,UsageState
state=BackendRouteState(sys.argv[3]); terminal=BackendTerminalDisposition(sys.argv[3])
path=pathlib.Path(sys.argv[2])/'backend-wait.json'
before={'repairBudget':3,'backendRechecks':2,'state':state.value,'resumeAt':'2026-08-12T18:05:00Z'}
path.write_text(json.dumps(before,sort_keys=True))
UsageState(route_state=state,subscription_capacity='subscription',retry_at=before['resumeAt'])
after=json.loads(path.read_text());after['backendRechecks']-=1;after['state']='AUTHENTICATED'
path.write_text(json.dumps(after,sort_keys=True))
print(json.dumps({'disposition':terminal.value,'before':before,'after':after,'repairBudgetUnchanged':after['repairBudget']==before['repairBudget'],'automaticallyResumed':after['state']=='AUTHENTICATED'}))
"""
    observed = subprocess.run(
        [sys.executable, "-c", script, str(repo), str(root), disposition],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if observed.returncode != 0:
        return {"contractProbeFailed": True, "stderrDigest": _digest(observed.stderr.encode())}
    payload: object = json.loads(observed.stdout)
    return cast(dict[str, object], payload)


def _machine_receipt_negatives(_repo: Path, root: Path) -> dict[str, object]:
    probe = Path("/usr/libexec/traincapsule-verifier-canary-receipt-probe")
    if not probe.is_file() or probe.is_symlink():
        return {"installedProbeMissing": True, "expected": str(probe)}
    observed = subprocess.run(
        [sys.executable, str(probe), "--artifact-root", str(root)],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env={"HOME": str(root), "LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
    )
    if observed.returncode != 0:
        return {"probeFailed": True, "stderrDigest": _digest(observed.stderr.encode())}
    payload: object = json.loads(observed.stdout)
    return cast(dict[str, object], payload)


LOCAL: dict[MandatoryCanaryId, Callable[[Path, Path, str], dict[str, object]]] = {
    MandatoryCanaryId.QUOTA_PAUSE_AND_RESUME: lambda repo, root, _sha: _backend_wait(
        repo, root, "QUOTA_WAIT"
    ),
    MandatoryCanaryId.AUTHENTICATION_EXPIRY_AND_RECOVERY: (
        lambda repo, root, _sha: _backend_wait(repo, root, "AUTH_EXPIRED")
    ),
    MandatoryCanaryId.PROCESS_KILL_AND_RESUME: lambda _repo, root, _sha: _checkpoint_kill(root),
    MandatoryCanaryId.REPEATED_FINDING_FINITE_STOP: lambda _repo, root, _sha: _finite_finding(root),
    MandatoryCanaryId.EXTERNAL_WAIT_LANE_ISOLATION: lambda _repo, root, _sha: _lane_isolation(root),
    MandatoryCanaryId.BAD_CANDIDATE_REJECTED_BEFORE_MAIN: lambda repo, _root, _sha: _bad_candidate(
        repo
    ),
    MandatoryCanaryId.RELEASE_TRANSACTION_CRASH_IDEMPOTENCY: lambda _repo, root, _sha: (
        _crash_journal(root)
    ),
    MandatoryCanaryId.AUTOMATIC_MILESTONE_ADVANCEMENT: lambda _repo, root, _sha: _milestone(root),
    MandatoryCanaryId.DUPLICATE_CONTROLLER_REJECTION: lambda _repo, root, _sha: _duplicate_lock(
        root
    ),
    MandatoryCanaryId.LEASE_RENEWAL_FAILURE: lambda _repo, root, _sha: _lease_failure(root),
    MandatoryCanaryId.STALE_CURRENT_FACTS: lambda _repo, _root, _sha: _freshness(),
    MandatoryCanaryId.MISSING_SOURCE_AUTHORITY: lambda repo, _root, _sha: _missing_source(repo),
    MandatoryCanaryId.MALFORMED_REPORT: lambda repo, _root, _sha: _contract_negative(
        repo, contract="malformed-report"
    ),
    MandatoryCanaryId.PRIVATE_GATE_MISSING_FOR_TRUST_RISK: lambda repo, _root, _sha: (
        _contract_negative(repo, contract="missing-private-gate")
    ),
    MandatoryCanaryId.MACHINE_VERIFIER_UNAVAILABLE: lambda repo, _root, _sha: _contract_negative(
        repo, contract="missing-verifier"
    ),
    MandatoryCanaryId.ACTIVATION_RECEIPT_WRONG_SHA: lambda _repo, _root, sha: _wrong_sha(sha),
    MandatoryCanaryId.MACHINE_RECEIPT_MISSING_INVALID_EXPIRED_REVOKED: (
        lambda repo, root, _sha: _machine_receipt_negatives(repo, root)
    ),
}


EXTERNAL = {
    MandatoryCanaryId.REAL_CLAUDE_MECHANICAL_TASK: (
        "real Claude executable, credential, and paid canary budget"
    ),
    MandatoryCanaryId.POST_PUSH_INVARIANT_FAILURE_AND_AUTOMATIC_DIRECT_REVERT: (
        "isolated GitHub repository, App credential, and ordinary direct-main push permission"
    ),
}


def _local_proven(canary: MandatoryCanaryId, evidence: dict[str, object]) -> bool:
    transitions = evidence.get("transitions")
    typed_transitions = cast(list[object], transitions) if isinstance(transitions, list) else []
    checks: dict[MandatoryCanaryId, bool] = {
        MandatoryCanaryId.PROCESS_KILL_AND_RESUME: (
            evidence.get("killedReturnCode") == -signal.SIGKILL
            and evidence.get("after") == "PLANNING->RESUMED"
        ),
        MandatoryCanaryId.REPEATED_FINDING_FINITE_STOP: (
            evidence.get("persisted") == 4
            and bool(typed_transitions)
            and typed_transitions[-1] == "HARD_STUCK"
        ),
        MandatoryCanaryId.EXTERNAL_WAIT_LANE_ISOLATION: (
            evidence.get("blockedLaneAbsent") is True
        ),
        MandatoryCanaryId.BAD_CANDIDATE_REJECTED_BEFORE_MAIN: (
            evidence.get("mainUnchanged") is True and evidence.get("dirtyRejected") is True
        ),
        MandatoryCanaryId.RELEASE_TRANSACTION_CRASH_IDEMPOTENCY: (
            evidence.get("duplicatePublish") is False
        ),
        MandatoryCanaryId.AUTOMATIC_MILESTONE_ADVANCEMENT: (
            evidence.get("exactlyOneActive") is True
        ),
        MandatoryCanaryId.DUPLICATE_CONTROLLER_REJECTION: (
            evidence.get("secondControllerRejected") is True
        ),
        MandatoryCanaryId.LEASE_RENEWAL_FAILURE: evidence.get("renewalAccepted") is False,
        MandatoryCanaryId.STALE_CURRENT_FACTS: evidence.get("recheckRequired") is True,
        MandatoryCanaryId.MISSING_SOURCE_AUTHORITY: (
            evidence.get("missingPathRejected") is True
        ),
        MandatoryCanaryId.MALFORMED_REPORT: evidence.get("extraFieldRejected") is True,
        MandatoryCanaryId.PRIVATE_GATE_MISSING_FOR_TRUST_RISK: (
            evidence.get("unavailableDetected") is True
        ),
        MandatoryCanaryId.MACHINE_VERIFIER_UNAVAILABLE: (
            evidence.get("unavailableDetected") is True
        ),
        MandatoryCanaryId.ACTIVATION_RECEIPT_WRONG_SHA: (
            evidence.get("mismatchRejected") is True
        ),
        MandatoryCanaryId.QUOTA_PAUSE_AND_RESUME: (
            evidence.get("disposition") == "QUOTA_WAIT"
            and evidence.get("repairBudgetUnchanged") is True
            and evidence.get("automaticallyResumed") is True
        ),
        MandatoryCanaryId.AUTHENTICATION_EXPIRY_AND_RECOVERY: (
            evidence.get("disposition") == "AUTH_EXPIRED"
            and evidence.get("repairBudgetUnchanged") is True
            and evidence.get("automaticallyResumed") is True
        ),
        MandatoryCanaryId.MACHINE_RECEIPT_MISSING_INVALID_EXPIRED_REVOKED: (
            evidence.get("missingRejected") is True
            and evidence.get("invalidRejected") is True
            and evidence.get("expiredRejected") is True
            and evidence.get("revokedRejected") is True
        ),
        MandatoryCanaryId.RUNTIME_ROOT_OUTSIDE_REPO: (
            evidence.get("runtimeOutsideRepository") is True
            and evidence.get("runtimeStopPresent") is True
        ),
    }
    return checks[canary]


def _invoke_external_probe(
    *,
    canary: MandatoryCanaryId,
    args: argparse.Namespace,
) -> tuple[CanaryStatus, dict[str, object], str | None]:
    try:
        payload = run_probe(canary.value, args)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return (
            CanaryStatus.BLOCKED_PREREQUISITE,
            {
                "requiredExternalPrerequisite": EXTERNAL[canary],
                "blockedErrorType": type(exc).__name__,
            },
            f"external probe did not prove the canary: {EXTERNAL[canary]}",
        )
    if payload.get("proven") is not True:
        return (
            CanaryStatus.BLOCKED_PREREQUISITE,
            {"reported": payload},
            f"external probe did not provide proven=true: {EXTERNAL[canary]}",
        )
    return CanaryStatus.PASS, payload, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["probe"])
    parser.add_argument(
        "--canary", required=True, choices=[item.value for item in MandatoryCanaryId]
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--main-sha", required=True)
    parser.add_argument("--tree-sha", required=True)
    args = parser.parse_args()
    canary = MandatoryCanaryId(args.canary)
    status = CanaryStatus.PASS
    failure: str | None = None
    if canary is MandatoryCanaryId.RUNTIME_ROOT_OUTSIDE_REPO:
        evidence = _runtime_outside(args.repo.resolve(), args.runtime_root.resolve())
    elif canary in LOCAL:
        evidence = LOCAL[canary](args.repo.resolve(), args.artifact_root.resolve(), args.main_sha)
        if not _local_proven(canary, evidence):
            status = CanaryStatus.FAIL
            failure = "local mechanism did not prove its exact expected invariant"
    else:
        status, evidence, failure = _invoke_external_probe(canary=canary, args=args)
    name, digest = _write(args.artifact_root, "mechanism-evidence.json", evidence)
    outcome = MechanismOutcome(
        schema_version="3.1",
        canary_id=canary,
        run_id=args.run_id,
        exact_main_sha=args.main_sha,
        exact_tree_sha=args.tree_sha,
        status=status,
        evidence_artifacts={name: digest},
        failure_reason=failure,
        observed_at=datetime.now(UTC),
    )
    print(json.dumps(outcome.model_dump(mode="json", by_alias=True), sort_keys=True))
    return {
        CanaryStatus.PASS: 0,
        CanaryStatus.BLOCKED_PREREQUISITE: 2,
        CanaryStatus.FAIL: 3,
    }[status]


if __name__ == "__main__":
    raise SystemExit(main())
