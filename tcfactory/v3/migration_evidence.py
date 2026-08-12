"""Strict, independently auditable evidence for the V3 migration milestone."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal, cast

from pydantic import ConfigDict, Field, RootModel, model_validator

from tcfactory.util import sha256_file
from tcfactory.v3.base import SHA_PATTERN, V3Model
from tcfactory.v3.source_authority import validate_active_source_generation

DIGEST_HEX_PATTERN = r"^[0-9a-f]{64}$"
M0_EVIDENCE_IDS = (
    "V3-MIG-016",
    "V3-MIG-017",
    "V3-MIG-018",
    "V3-MIG-019",
    "V3-MIG-020",
)
M0_PREREQUISITE_IDS = M0_EVIDENCE_IDS[:-1]
EVIDENCE_ROOT = Path("docs/migrations/evidence/v3.1-zh")
HISTORICAL_V3_EVIDENCE_ROOT = Path("docs/migrations/evidence")
TRANSCRIPT_ROOT = EVIDENCE_ROOT / "transcripts"

EXPECTED_EVIDENCE_TYPES: dict[str, str] = {
    "V3-MIG-016": "SIGNED_SOURCE_MIGRATION_MACHINE_AUTHORIZATION",
    "V3-MIG-017": "READ_ONLY_ROLLBACK_REHEARSAL",
    "V3-MIG-018": "NON_MUTATING_CONTROLLER_OBSERVATION",
    "V3-MIG-019": "AUTOMATED_PR_REQUIRED_CI_MERGED_MAIN_ACCEPTANCE",
    "V3-MIG-020": "M0_COMPLETION_RECORD",
}
EXPECTED_EXECUTIONS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "V3-MIG-016": (
        (
            "source-authority-integrity",
            (".venv/bin/python", "scripts/gates/source_of_truth_integrity.py"),
        ),
        (
            "active-policy-integrity",
            (".venv/bin/python", "scripts/gates/active_policy_integrity.py"),
        ),
        (
            "authoritative-bundle-integrity",
            (
                ".venv/bin/python",
                "scripts/gates/v3_bundle_integrity.py",
                "--check-report",
            ),
        ),
    ),
    "V3-MIG-017": (
        (
            "rollback-archive-rehearsal",
            (".venv/bin/python", "scripts/gates/v3_rollback_rehearsal.py"),
        ),
    ),
    "V3-MIG-018": (
        (
            "controller-observation-contracts",
            (
                ".venv/bin/pytest",
                "tests/test_v3_config_and_roadmap.py",
                "tests/test_v3_scheduler_and_recovery.py",
                "tests/test_v3_supervisor_and_status.py",
            ),
        ),
    ),
    "V3-MIG-019": (
        (
            "controller-simulation",
            (".venv/bin/pytest", "tests/test_v3_controller_simulation.py"),
        ),
    ),
    "V3-MIG-020": (
        (
            "complete-pre-evidence-acceptance",
            ("bash", "scripts/gates/full_quality.sh", "--pre-evidence"),
        ),
    ),
}
FINAL_EVIDENCE_SCHEMA_RULES: list[dict[str, Any]] = [
    {
        "if": {"properties": {"workItemId": {"const": work_item_id}}},
        "then": {
            "properties": {
                "evidenceType": {"const": EXPECTED_EVIDENCE_TYPES[work_item_id]},
                "executions": {
                    "prefixItems": [
                        {
                            "properties": {
                                "commandId": {"const": command_id},
                                "command": {"const": list(command)},
                            }
                        }
                        for command_id, command in executions
                    ],
                    "minItems": len(executions),
                    "maxItems": len(executions),
                },
            }
        },
    }
    for work_item_id, executions in EXPECTED_EXECUTIONS.items()
]

_NONRECURSIVE_EXCLUSIONS = {
    "docs/migrations/V3_CODEX_EXECUTION_STATE.md",
    "docs/migrations/V3_MIGRATION_REPORT.md",
    "docs/migrations/V3_TEST_MATRIX.md",
}
_UNTRACKED_IMPLEMENTATION_PREFIXES = (
    ".github/",
    "config/",
    "docs/migrations/",
    "factory/policy/",
    "factory/roadmap/",
    "packages/",
    "prompts/",
    "schemas/",
    "scripts/",
    "tcfactory/",
    "tests/",
)


class MigrationEvidenceError(RuntimeError):
    """The M0 evidence set is missing, mutable, or internally inconsistent."""


class EvidenceBinding(V3Model):
    """Bind evidence without recursively hashing the evidence files themselves."""

    subject_sha: str | None = Field(default=None, pattern=SHA_PATTERN.pattern)
    implementation_tree_sha256: str | None = Field(
        default=None, pattern=DIGEST_HEX_PATTERN
    )
    implementation_tree_file_count: int | None = Field(default=None, ge=1)
    algorithm: Literal["git-commit-sha1", "sha256-mode-path-blob-manifest"]

    @model_validator(mode="after")
    def require_exactly_one_nonrecursive_binding(self) -> EvidenceBinding:
        if (self.subject_sha is None) == (self.implementation_tree_sha256 is None):
            raise ValueError(
                "evidence requires exactly one subjectSha or implementationTreeSha256"
            )
        if self.subject_sha is not None:
            if (
                self.algorithm != "git-commit-sha1"
                or self.implementation_tree_file_count is not None
            ):
                raise ValueError("subjectSha requires the git-commit-sha1 binding only")
        elif (
            self.algorithm != "sha256-mode-path-blob-manifest"
            or self.implementation_tree_file_count is None
        ):
            raise ValueError(
                "implementationTreeSha256 requires its file count and manifest algorithm"
            )
        return self


class AuthorityDigests(V3Model):
    """Exact active authority bytes under which an observation was accepted."""

    source_manifest_sha256: str = Field(pattern=DIGEST_HEX_PATTERN)
    active_generation_sha256: str = Field(pattern=DIGEST_HEX_PATTERN)
    source_generation_sha256: str = Field(pattern=DIGEST_HEX_PATTERN)


class EvidenceExecution(V3Model):
    """One replayable command and its immutable output transcript."""

    command_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,63}$")
    command: list[str] = Field(min_length=2, max_length=32)
    working_directory: Literal["."] = "."
    exit_code: int = Field(ge=0, le=255)
    result: Literal["PASS", "FAIL"]
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    failure_attribution: Literal[
        "NONE", "PRE_EXISTING", "INTRODUCED", "INFRASTRUCTURE", "UNKNOWN"
    ]
    transcript_path: str = Field(min_length=1)
    transcript_sha256: str = Field(pattern=DIGEST_HEX_PATTERN)

    @model_validator(mode="after")
    def result_matches_process_outcome(self) -> EvidenceExecution:
        if self.result == "PASS":
            if self.exit_code != 0 or self.failed_count != 0:
                raise ValueError("PASS requires exitCode 0 and failedCount 0")
            if self.failure_attribution != "NONE":
                raise ValueError("PASS requires failureAttribution NONE")
        elif self.exit_code == 0 and self.failed_count == 0:
            raise ValueError("FAIL requires a nonzero exitCode or failedCount")
        elif self.failure_attribution == "NONE":
            raise ValueError("FAIL requires explicit failure attribution")
        return self


class IndependentReceiptSignature(V3Model):
    algorithm: Literal["ed25519"]
    key_id: str = Field(min_length=1)
    value: str = Field(min_length=32)


class IndependentReceiptAuthority(V3Model):
    issuer: Literal["INDEPENDENT_MACHINE_VERIFIER"]
    issued_at: datetime
    expires_at: datetime
    nonce: str = Field(min_length=16)
    revocation_epoch: int = Field(ge=0)
    signature: IndependentReceiptSignature

    @model_validator(mode="after")
    def validate_window(self) -> IndependentReceiptAuthority:
        if self.expires_at <= self.issued_at:
            raise ValueError("independent receipt expiry must follow issuance")
        return self


class SourceMigrationAuthorization(IndependentReceiptAuthority):
    receipt_type: Literal["V3_1_SOURCE_MIGRATION_AUTHORIZATION"]
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    active_generation_digest: str = Field(pattern=DIGEST_HEX_PATTERN)
    source_manifest_digest: str = Field(pattern=DIGEST_HEX_PATTERN)
    source_generation_digest: str = Field(pattern=DIGEST_HEX_PATTERN)


class RequiredCheckReceipt(V3Model):
    name: Literal[
        "Factory quality",
        "Packaging install",
        "Product CI",
        "Security",
        "Docs and schemas",
        "Source-of-truth integrity",
        "Source freshness",
    ]
    conclusion: Literal["success"]
    observed_sha: str = Field(pattern=SHA_PATTERN.pattern)


class PullRequestAcceptanceReceipt(IndependentReceiptAuthority):
    receipt_type: Literal["V3_1_PR_PUBLICATION"]
    task_class: Literal["MECHANICAL", "STANDARD"]
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    pull_request_url: str = Field(pattern=r"^https://github\.com/.+/pull/[0-9]+$")
    pull_request_head_sha: str = Field(pattern=SHA_PATTERN.pattern)
    merged_main_sha: str = Field(pattern=SHA_PATTERN.pattern)
    active_generation_digest: str = Field(pattern=DIGEST_HEX_PATTERN)
    source_manifest_digest: str = Field(pattern=DIGEST_HEX_PATTERN)
    required_checks: list[RequiredCheckReceipt] = Field(min_length=7, max_length=7)

    @model_validator(mode="after")
    def validate_exact_sha_and_checks(self) -> PullRequestAcceptanceReceipt:
        if not (
            self.pull_request_head_sha == self.candidate_sha == self.merged_main_sha
        ):
            raise ValueError("PR receipt must bind one exact candidate/head/merged-main SHA")
        names = [check.name for check in self.required_checks]
        if len(names) != len(set(names)):
            raise ValueError("PR receipt required checks must be unique")
        if any(check.observed_sha != self.candidate_sha for check in self.required_checks):
            raise ValueError("PR receipt check result is not bound to the candidate SHA")
        return self


class RecoveryRehearsalReceipt(IndependentReceiptAuthority):
    receipt_type: Literal["V3_1_RECOVERY_REHEARSAL"]
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    restored_exact_sha: Literal[True]
    outcome: Literal["PASSED"]


class FinalMigrationEvidence(V3Model):
    """Final M0 record; a PASS is replayable rather than self-attesting."""

    model_config = ConfigDict(
        json_schema_extra=cast(dict[str, Any], {"allOf": FINAL_EVIDENCE_SCHEMA_RULES})
    )

    schema_version: Literal[2] = 2
    work_item_id: str = Field(pattern=r"^V3-MIG-0(?:1[6-9]|20)$")
    status: Literal["FINAL"] = "FINAL"
    result: Literal["PASS", "FAIL"]
    evidence_type: str = Field(min_length=3)
    recorded_at: datetime
    binding: EvidenceBinding
    authority_digests: AuthorityDigests
    executions: list[EvidenceExecution] = Field(min_length=1, max_length=8)
    evidence_inputs: dict[str, str] = Field(default_factory=dict[str, str], max_length=8)
    truth_boundary: str = Field(min_length=12)
    source_migration_authorization: SourceMigrationAuthorization | None
    pr_acceptance_receipts: list[PullRequestAcceptanceReceipt]
    recovery_rehearsal_receipt: RecoveryRehearsalReceipt | None

    @model_validator(mode="after")
    def validate_completion_and_result(self) -> FinalMigrationEvidence:
        if self.work_item_id in self.evidence_inputs:
            raise ValueError("migration evidence cannot cite itself")
        if any(
            not re.fullmatch(DIGEST_HEX_PATTERN, value)
            for value in self.evidence_inputs.values()
        ):
            raise ValueError("evidenceInputs require raw SHA-256 hex digests")
        if self.result == "PASS" and any(item.result != "PASS" for item in self.executions):
            raise ValueError("a PASS evidence record cannot contain a failed execution")
        if self.result == "FAIL" and all(item.result == "PASS" for item in self.executions):
            raise ValueError("a FAIL evidence record requires at least one failed execution")
        expected_type = EXPECTED_EVIDENCE_TYPES[self.work_item_id]
        if self.evidence_type != expected_type:
            raise ValueError(
                f"{self.work_item_id} evidenceType must be exactly {expected_type}"
            )
        observed_executions = tuple(
            (execution.command_id, tuple(execution.command)) for execution in self.executions
        )
        if observed_executions != EXPECTED_EXECUTIONS[self.work_item_id]:
            raise ValueError(f"{self.work_item_id} execution command set is not authoritative")
        if self.work_item_id == "V3-MIG-020":
            if set(self.evidence_inputs) != set(M0_PREREQUISITE_IDS):
                raise ValueError("V3-MIG-020 must bind exactly V3-MIG-016 through V3-MIG-019")
        elif self.evidence_inputs:
            raise ValueError("only V3-MIG-020 may bind prerequisite M0 evidence")
        if self.work_item_id == "V3-MIG-016":
            if self.source_migration_authorization is None:
                raise ValueError("V3-MIG-016 requires an independent signed authorization")
            if self.pr_acceptance_receipts or self.recovery_rehearsal_receipt is not None:
                raise ValueError("V3-MIG-016 may contain only source-migration authorization")
        elif self.work_item_id == "V3-MIG-019":
            if self.source_migration_authorization is not None:
                raise ValueError("V3-MIG-019 cannot contain source-migration authorization")
            if self.recovery_rehearsal_receipt is not None:
                raise ValueError("V3-MIG-019 cannot contain a recovery rehearsal")
            if {receipt.task_class for receipt in self.pr_acceptance_receipts} != {
                "MECHANICAL",
                "STANDARD",
            }:
                raise ValueError("V3-MIG-019 requires mechanical and standard PR receipts")
        elif self.work_item_id == "V3-MIG-017":
            if self.recovery_rehearsal_receipt is None:
                raise ValueError("V3-MIG-017 requires an independent recovery rehearsal receipt")
            if self.source_migration_authorization is not None or self.pr_acceptance_receipts:
                raise ValueError("V3-MIG-017 may contain only its rehearsal receipt")
        elif (
            self.source_migration_authorization is not None
            or self.pr_acceptance_receipts
            or self.recovery_rehearsal_receipt is not None
        ):
            raise ValueError("this evidence type cannot contain independent receipt artifacts")
        return self


class PendingMigrationEvidence(V3Model):
    """Explicitly incomplete record used while a final implementation tree is changing."""

    schema_version: Literal[2] = 2
    work_item_id: str = Field(pattern=r"^V3-MIG-0(?:1[6-9]|20)$")
    status: Literal["PENDING_FINALIZATION"] = "PENDING_FINALIZATION"
    finalization_command: list[str] = Field(min_length=2)
    reason: str = Field(min_length=12)


MigrationEvidence = Annotated[
    FinalMigrationEvidence | PendingMigrationEvidence,
    Field(discriminator="status"),
]


class MigrationEvidenceDocument(RootModel[MigrationEvidence]):
    """Generated JSON Schema entry point for final and fail-closed pending records."""

    model_config = ConfigDict(json_schema_extra={"additionalProperties": False})


def authority_digests(repo_root: Path) -> AuthorityDigests:
    """Hash the canonical V3.1 generation pointer and its verified source set."""

    active = validate_active_source_generation(repo_root)
    return AuthorityDigests(
        source_manifest_sha256=active.manifest_digest,
        active_generation_sha256=active.config_digest,
        source_generation_sha256=active.source_digest.removeprefix("sha256:"),
    )


def _git_paths(repo_root: Path, *arguments: str) -> set[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z", *arguments],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    return {
        value.decode("utf-8")
        for value in completed.stdout.split(b"\0")
        if value
    }


def _is_implementation_path(relative: str) -> bool:
    if relative.startswith(EVIDENCE_ROOT.as_posix() + "/"):
        return False
    return relative not in _NONRECURSIVE_EXCLUSIONS and not relative.endswith(".previous")


def _git_mode(path: Path) -> str:
    if path.is_symlink():
        return "120000"
    return "100755" if path.stat().st_mode & 0o111 else "100644"


def _dirty_implementation_paths(repo_root: Path) -> list[str]:
    changed = subprocess.run(
        ["git", "diff", "--name-only", "-z", "HEAD", "--", "."],
        cwd=repo_root,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    paths = {
        value.decode("utf-8")
        for value in changed
        if value and _is_implementation_path(value.decode("utf-8"))
    }
    paths.update(
        value.decode("utf-8")
        for value in untracked
        if value
        and value.decode("utf-8").startswith(_UNTRACKED_IMPLEMENTATION_PREFIXES)
        and _is_implementation_path(value.decode("utf-8"))
    )
    return sorted(paths)


def implementation_tree_binding(repo_root: Path) -> EvidenceBinding:
    """Hash active implementation blobs while excluding evidence/status recursion."""

    tracked = _git_paths(repo_root, "--cached")
    untracked = {
        path
        for path in _git_paths(repo_root, "--others", "--exclude-standard")
        if path.startswith(_UNTRACKED_IMPLEMENTATION_PREFIXES)
    }
    selected: list[str] = []
    for relative in tracked | untracked:
        if not _is_implementation_path(relative):
            continue
        path = repo_root / relative
        if path.is_file() or path.is_symlink():
            selected.append(relative)
    selected.sort()

    digest = hashlib.sha256()
    for relative in selected:
        path = repo_root / relative
        blob = os.readlink(path).encode("utf-8") if path.is_symlink() else path.read_bytes()
        digest.update(_git_mode(path).encode("ascii"))
        digest.update(b"\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(blob)).encode("ascii"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(blob).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return EvidenceBinding(
        implementation_tree_sha256=digest.hexdigest(),
        implementation_tree_file_count=len(selected),
        algorithm="sha256-mode-path-blob-manifest",
    )


def load_evidence(path: Path) -> FinalMigrationEvidence | PendingMigrationEvidence:
    try:
        raw = cast(object, json.loads(path.read_text(encoding="utf-8")))
        return MigrationEvidenceDocument.model_validate(raw).root
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise MigrationEvidenceError(f"invalid migration evidence {path}: {exc}") from exc


def transcript_counts(
    command: list[str], exit_code: int, stdout: str, stderr: str
) -> tuple[int, int]:
    """Derive result counts from process output rather than receipt assertions."""

    output = stdout + "\n" + stderr
    if any(Path(argument).name == "pytest" for argument in command):
        passed_matches = re.findall(r"(?:^|\s)(\d+) passed(?:,|\s|$)", output)
        failed_matches = re.findall(r"(?:^|\s)(\d+) failed(?:,|\s|$)", output)
        if exit_code == 0 and not passed_matches:
            raise MigrationEvidenceError("successful pytest transcript lacks a pass count")
        passed = int(passed_matches[-1]) if passed_matches else 0
        failed = int(failed_matches[-1]) if failed_matches else (1 if exit_code else 0)
        return passed, failed
    return (1, 0) if exit_code == 0 else (0, 1)


def _validate_transcript(repo_root: Path, execution: EvidenceExecution) -> None:
    relative = PurePosixPath(execution.transcript_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise MigrationEvidenceError("evidence transcript path escapes the repository")
    if not relative.as_posix().startswith(TRANSCRIPT_ROOT.as_posix() + "/"):
        raise MigrationEvidenceError("evidence transcript is outside the immutable transcript root")
    path = repo_root / relative
    if path.is_symlink():
        raise MigrationEvidenceError(f"evidence transcript cannot be a symlink: {relative}")
    if not path.is_file() or sha256_file(path) != execution.transcript_sha256:
        raise MigrationEvidenceError(f"missing or digest-mismatched transcript: {relative}")
    try:
        transcript = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationEvidenceError(f"unreadable transcript {relative}: {exc}") from exc
    if transcript.get("command") != execution.command:
        raise MigrationEvidenceError(f"transcript command mismatch: {relative}")
    if transcript.get("workingDirectory") != execution.working_directory:
        raise MigrationEvidenceError(f"transcript working directory mismatch: {relative}")
    if transcript.get("exitCode") != execution.exit_code:
        raise MigrationEvidenceError(f"transcript exit code mismatch: {relative}")
    stdout = transcript.get("stdout")
    stderr = transcript.get("stderr")
    if not isinstance(stdout, str) or not isinstance(stderr, str):
        raise MigrationEvidenceError(f"transcript lacks exact stdout/stderr: {relative}")
    passed_count = transcript.get("passedCount")
    failed_count = transcript.get("failedCount")
    derived = transcript_counts(execution.command, execution.exit_code, stdout, stderr)
    if (passed_count, failed_count) != derived:
        raise MigrationEvidenceError(f"transcript result count mismatch: {relative}")
    if (execution.passed_count, execution.failed_count) != derived:
        raise MigrationEvidenceError(f"evidence result count mismatch: {relative}")


def validate_repository_evidence(repo_root: Path, *, prerequisites_only: bool = False) -> int:
    """Validate exact bindings, authority digests, transcripts, and completion inputs."""

    ids = M0_PREREQUISITE_IDS if prerequisites_only else M0_EVIDENCE_IDS
    expected_authority = authority_digests(repo_root)
    expected_tree = implementation_tree_binding(repo_root)
    records: dict[str, FinalMigrationEvidence] = {}
    for work_item_id in ids:
        path = repo_root / EVIDENCE_ROOT / f"{work_item_id}.json"
        record = load_evidence(path)
        if isinstance(record, PendingMigrationEvidence):
            raise MigrationEvidenceError(
                f"{work_item_id} is pending; run {' '.join(record.finalization_command)}"
            )
        if record.work_item_id != work_item_id:
            raise MigrationEvidenceError(f"evidence filename/subject mismatch: {path}")
        if record.result != "PASS":
            raise MigrationEvidenceError(f"M0 evidence is not PASS: {work_item_id}")
        if record.authority_digests != expected_authority:
            raise MigrationEvidenceError(f"authority digest mismatch: {work_item_id}")
        if record.binding.subject_sha is not None:
            completed = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
            )
            if record.binding.subject_sha != completed.stdout.strip():
                raise MigrationEvidenceError(f"subject SHA mismatch: {work_item_id}")
            dirty = _dirty_implementation_paths(repo_root)
            if dirty:
                raise MigrationEvidenceError(
                    f"subject SHA has dirty/staged/untracked implementation paths: {dirty}"
                )
        elif record.binding != expected_tree:
            raise MigrationEvidenceError(f"implementation-tree digest mismatch: {work_item_id}")
        for execution in record.executions:
            _validate_transcript(repo_root, execution)
        records[work_item_id] = record

    if not prerequisites_only:
        completion = records["V3-MIG-020"]
        for work_item_id in M0_PREREQUISITE_IDS:
            actual = sha256_file(repo_root / EVIDENCE_ROOT / f"{work_item_id}.json")
            if completion.evidence_inputs.get(work_item_id) != actual:
                raise MigrationEvidenceError(
                    f"V3-MIG-020 prerequisite digest mismatch: {work_item_id}"
                )
    return len(records)
