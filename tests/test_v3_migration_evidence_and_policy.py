from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from scripts.gates.active_policy_integrity import ActivePolicyError, validate_active_policy
from scripts.gates.v3_bundle_integrity import (
    INSTALLED_IMMUTABLE_COPIES,
    REQUIRED_ROOT_PAYLOAD,
    BundleIntegrityError,
    build_report,
    validate_committed_report,
)
from tcfactory.util import sha256_file
from tcfactory.v3.migration_evidence import (
    EVIDENCE_ROOT,
    EXPECTED_EVIDENCE_TYPES,
    EXPECTED_EXECUTIONS,
    M0_EVIDENCE_IDS,
    M0_PREREQUISITE_IDS,
    AuthorityDigests,
    EvidenceBinding,
    EvidenceExecution,
    FinalMigrationEvidence,
    MigrationEvidenceDocument,
    MigrationEvidenceError,
    authority_digests,
    implementation_tree_binding,
    transcript_counts,
    validate_repository_evidence,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _initialize_evidence_repo(root: Path) -> None:
    _write(root / "SOURCE_PRECEDENCE.md", "owner authority\n")
    _write(root / "config/owner_directives.yaml", "owner\n")
    _write(root / "factory/policy/ZERO_HUMAN_OPERATION_OVERRIDE.json", "{}\n")
    _write(
        root / "docs/source-of-truth/v3-2026-08-11/FINAL_MANIFEST_V3.json", "{}\n"
    )
    _write(root / "tcfactory/v3/example.py", "VALUE = 3\n")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)


def _final_record(
    root: Path,
    work_item_id: str,
    authority: AuthorityDigests,
    *,
    evidence_inputs: dict[str, str] | None = None,
    binding: EvidenceBinding | None = None,
) -> FinalMigrationEvidence:
    executions: list[EvidenceExecution] = []
    for index, (command_id, expected_command) in enumerate(
        EXPECTED_EXECUTIONS[work_item_id], start=1
    ):
        command = list(expected_command)
        stdout = "1 passed in 0.01s\n" if any(
            Path(argument).name == "pytest" for argument in command
        ) else "PASS\n"
        passed_count, failed_count = transcript_counts(command, 0, stdout, "")
        transcript = (
            root
            / EVIDENCE_ROOT
            / "transcripts"
            / f"{work_item_id}-{index:02d}-{command_id}.json"
        )
        _write(
            transcript,
            json.dumps(
                {
                    "transcriptVersion": 1,
                    "command": command,
                    "workingDirectory": ".",
                    "exitCode": 0,
                    "passedCount": passed_count,
                    "failedCount": failed_count,
                    "stdout": stdout,
                    "stderr": "",
                },
                indent=2,
            )
            + "\n",
        )
        executions.append(
            EvidenceExecution(
                command_id=command_id,
                command=command,
                exit_code=0,
                result="PASS",
                passed_count=passed_count,
                failed_count=failed_count,
                failure_attribution="NONE",
                transcript_path=transcript.relative_to(root).as_posix(),
                transcript_sha256=sha256_file(transcript),
            )
        )
    return FinalMigrationEvidence(
        work_item_id=work_item_id,
        result="PASS",
        evidence_type=EXPECTED_EVIDENCE_TYPES[work_item_id],
        recorded_at=datetime.now(UTC),
        binding=binding or implementation_tree_binding(root),
        authority_digests=authority,
        executions=executions,
        evidence_inputs=evidence_inputs or {},
        truth_boundary="Controlled test evidence creates no external facts.",
    )


def _write_evidence_set(root: Path) -> None:
    authority = authority_digests(root)
    for work_item_id in M0_PREREQUISITE_IDS:
        record = _final_record(root, work_item_id, authority)
        _write(
            root / EVIDENCE_ROOT / f"{work_item_id}.json",
            json.dumps(record.model_dump(mode="json", by_alias=True), indent=2) + "\n",
        )
    inputs = {
        work_item_id: sha256_file(root / EVIDENCE_ROOT / f"{work_item_id}.json")
        for work_item_id in M0_PREREQUISITE_IDS
    }
    completion = _final_record(root, "V3-MIG-020", authority, evidence_inputs=inputs)
    _write(
        root / EVIDENCE_ROOT / "V3-MIG-020.json",
        json.dumps(completion.model_dump(mode="json", by_alias=True), indent=2) + "\n",
    )


def test_m0_evidence_is_nonrecursive_exact_and_tamper_evident(tmp_path: Path) -> None:
    _initialize_evidence_repo(tmp_path)
    _write_evidence_set(tmp_path)
    assert validate_repository_evidence(tmp_path) == len(M0_EVIDENCE_IDS)

    record = json.loads(
        (tmp_path / EVIDENCE_ROOT / "V3-MIG-019.json").read_text(encoding="utf-8")
    )
    transcript = tmp_path / record["executions"][0]["transcriptPath"]
    transcript.write_text(transcript.read_text(encoding="utf-8") + "tamper", encoding="utf-8")
    with pytest.raises(MigrationEvidenceError, match="transcript"):
        validate_repository_evidence(tmp_path)


def test_m0_evidence_rejects_missing_fields_authority_mismatch_and_self_reference(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValidationError):
        MigrationEvidenceDocument.model_validate(
            {"schemaVersion": 2, "workItemId": "V3-MIG-016", "status": "FINAL"}
        )

    _initialize_evidence_repo(tmp_path)
    _write_evidence_set(tmp_path)
    owner = tmp_path / "config/owner_directives.yaml"
    owner.write_text("changed owner\n", encoding="utf-8")
    with pytest.raises(MigrationEvidenceError, match="authority digest mismatch"):
        validate_repository_evidence(tmp_path)

    authority = authority_digests(tmp_path)
    with pytest.raises(ValidationError, match="cannot cite itself"):
        _final_record(
            tmp_path,
            "V3-MIG-020",
            authority,
            evidence_inputs={
                **{work_item_id: "0" * 64 for work_item_id in M0_PREREQUISITE_IDS},
                "V3-MIG-020": "0" * 64,
            },
        )


def test_m0_evidence_rejects_wrong_command_type_count_and_dirty_subject_sha(
    tmp_path: Path,
) -> None:
    _initialize_evidence_repo(tmp_path)
    authority = authority_digests(tmp_path)
    record = _final_record(tmp_path, "V3-MIG-016", authority)
    payload = record.model_dump(mode="json", by_alias=True)
    payload["evidenceType"] = "SELF_ASSERTED_PASS"
    with pytest.raises(ValidationError, match="evidenceType must be exactly"):
        FinalMigrationEvidence.model_validate(payload)

    payload = record.model_dump(mode="json", by_alias=True)
    payload["executions"][0]["command"] = ["python", "-c", "print('PASS')"]
    with pytest.raises(ValidationError, match="command set is not authoritative"):
        FinalMigrationEvidence.model_validate(payload)

    schema = FinalMigrationEvidence.model_json_schema(by_alias=True)
    raw_rules = schema.get("allOf")
    assert isinstance(raw_rules, list)
    rules = cast(list[dict[str, Any]], raw_rules)
    assert len(rules) == len(M0_EVIDENCE_IDS)
    completion_rule = next(
        rule
        for rule in rules
        if rule["if"]["properties"]["workItemId"]["const"] == "V3-MIG-020"
    )
    assert completion_rule["then"]["properties"]["evidenceType"]["const"] == (
        "M0_COMPLETION_RECORD"
    )
    assert completion_rule["then"]["properties"]["executions"]["prefixItems"][0][
        "properties"
    ]["command"]["const"] == ["bash", "scripts/gates/full_quality.sh", "--pre-evidence"]

    _write_evidence_set(tmp_path)
    path = tmp_path / EVIDENCE_ROOT / "V3-MIG-018.json"
    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["executions"][0]["passedCount"] = 999
    _write(path, json.dumps(tampered, indent=2) + "\n")
    with pytest.raises(MigrationEvidenceError, match="evidence result count mismatch"):
        validate_repository_evidence(tmp_path)

    subprocess.run(
        [
            "git",
            "-c",
            "user.name=TrainCapsule Test",
            "-c",
            "user.email=test@invalid.local",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=tmp_path,
        check=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _write_evidence_set(tmp_path)
    _write(tmp_path / "scripts/new_active_gate.py", "VALUE = 1\n")
    subject_record = _final_record(
        tmp_path,
        "V3-MIG-016",
        authority_digests(tmp_path),
        binding=EvidenceBinding(subject_sha=head, algorithm="git-commit-sha1"),
    )
    _write(
        tmp_path / EVIDENCE_ROOT / "V3-MIG-016.json",
        json.dumps(subject_record.model_dump(mode="json", by_alias=True), indent=2) + "\n",
    )
    with pytest.raises(MigrationEvidenceError, match="dirty/staged/untracked"):
        validate_repository_evidence(tmp_path, prerequisites_only=True)
    (tmp_path / "scripts/new_active_gate.py").unlink()
    _write(tmp_path / "local-notes.tmp", "untracked non-implementation note\n")
    assert validate_repository_evidence(tmp_path, prerequisites_only=True) == len(
        M0_PREREQUISITE_IDS
    )


def test_implementation_tree_binding_includes_executable_mode(tmp_path: Path) -> None:
    _initialize_evidence_repo(tmp_path)
    script = tmp_path / "scripts/check.sh"
    _write(script, "#!/usr/bin/env bash\nexit 0\n")
    script.chmod(0o644)
    regular = implementation_tree_binding(tmp_path)
    script.chmod(0o755)
    executable = implementation_tree_binding(tmp_path)
    assert regular.implementation_tree_sha256 != executable.implementation_tree_sha256


def test_m0_completion_uses_non_circular_complete_acceptance() -> None:
    assert EXPECTED_EXECUTIONS["V3-MIG-020"] == (
        (
            "complete-pre-evidence-acceptance",
            ("bash", "scripts/gates/full_quality.sh", "--pre-evidence"),
        ),
    )
    gate = (Path(__file__).resolve().parents[1] / "scripts/gates/full_quality.sh").read_text(
        encoding="utf-8"
    )
    assert 'if [[ $EVIDENCE_MODE == "validate" ]]' in gate
    assert "scripts/gates/v3_migration_evidence.py" in gate
    for required in (
        "ruff check .",
        "pyright",
        "python -m pytest -q",
        "scripts/generate_v3_schemas.py --check",
        "scripts/generate_v3_roadmap.py --check",
        "scripts/generate_v3_legacy_migration.py --check",
        "scripts/generate_product_schemas.py --check",
        "scripts/update_v3_migration_inventory.py --check",
        "tcfactory config validate",
        "tcfactory migrate-roadmap --from-v2 --dry-run",
        "build --offline --wheel",
    ):
        assert required in gate


def test_active_policy_gate_rejects_human_and_pr_dependencies(tmp_path: Path) -> None:
    _write(
        tmp_path / "config/owner_directives.yaml",
        "\n".join(
            (
                "humanIntervention: FORBIDDEN",
                "publicationBranch: main",
                "nonMainPushes: FORBIDDEN",
                "pullRequestDependency: FORBIDDEN",
            )
        )
        + "\n",
    )
    _write(tmp_path / "prompts/global.md", "ownerClass: PRODUCT | HUMAN\n")
    with pytest.raises(ActivePolicyError, match="human finding owner"):
        validate_active_policy(tmp_path)

    _write(tmp_path / "prompts/global.md", "ownerClass: PRODUCT | FACTORY | EXTERNAL\n")
    _write(tmp_path / "prompts/release.md", "Release is draft-pull-request only.\n")
    with pytest.raises(ActivePolicyError, match="PR-only release"):
        validate_active_policy(tmp_path)

    _write(tmp_path / "prompts/release.md", "Controller promotes exact SHA to main only.\n")
    assert validate_active_policy(tmp_path) == 3

    _write(
        tmp_path / "tcfactory/cli.py",
        "POLICY = 'main-only forbidden; release is PR-first'\n",
    )
    with pytest.raises(ActivePolicyError, match="PR-only release"):
        validate_active_policy(tmp_path)


def _fake_authoritative_bundle(root: Path, active: Path) -> None:
    payload = {**{name: f"authoritative {name}\n" for name in REQUIRED_ROOT_PAYLOAD}}
    payload["examples/example.json"] = '{"example": true}\n'
    records: list[dict[str, object]] = []
    for relative, content in sorted(payload.items()):
        path = root / relative
        _write(path, content)
        blob = path.read_bytes()
        records.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(blob).hexdigest(),
                "bytes": len(blob),
                "category": "example" if relative.startswith("examples/") else "normative",
            }
        )
        if relative in INSTALLED_IMMUTABLE_COPIES:
            _write(active / relative, content)
    manifest = {
        "selfHashIncluded": False,
        "fileCountExcludingManifest": len(records),
        "totalBytesExcludingManifest": sum(
            len(content.encode("utf-8")) for content in payload.values()
        ),
        "files": records,
    }
    _write(root / "FINAL_MANIFEST_V3.json", json.dumps(manifest, indent=2) + "\n")


def test_full_bundle_report_covers_every_file_and_detects_copy_tamper(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    active = tmp_path / "active"
    _fake_authoritative_bundle(bundle, active)
    manifest_digest = sha256_file(bundle / "FINAL_MANIFEST_V3.json")
    expected_count = len(REQUIRED_ROOT_PAYLOAD) + 1
    expected_bytes = sum(
        path.stat().st_size
        for path in bundle.rglob("*")
        if path.is_file() and path.name != "FINAL_MANIFEST_V3.json"
    )
    report = build_report(
        bundle,
        active,
        expected_manifest_sha256=manifest_digest,
        expected_file_count=expected_count,
        expected_total_bytes=expected_bytes,
    )
    assert report["fileCountExcludingManifest"] == len(REQUIRED_ROOT_PAYLOAD) + 1
    report_path = tmp_path / "report.json"
    _write(report_path, json.dumps(report, indent=2) + "\n")
    assert (
        validate_committed_report(
            report_path,
            active_bundle=active,
            expected_manifest_sha256=manifest_digest,
            expected_file_count=expected_count,
            expected_total_bytes=expected_bytes,
        )
        == expected_count
    )

    changed = active / next(iter(INSTALLED_IMMUTABLE_COPIES))
    changed.write_text("tamper\n", encoding="utf-8")
    with pytest.raises(BundleIntegrityError, match="installed-copy report mismatch"):
        validate_committed_report(
            report_path,
            active_bundle=active,
            expected_manifest_sha256=manifest_digest,
            expected_file_count=expected_count,
            expected_total_bytes=expected_bytes,
        )
