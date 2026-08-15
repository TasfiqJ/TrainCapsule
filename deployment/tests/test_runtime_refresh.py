from __future__ import annotations

import inspect
import os
import subprocess
import sys
from pathlib import Path

import pytest
from traincapsule_verifier.canonical import canonical_json_bytes, sha256_digest

from deployment.privileged_installer import RepositorySnapshotManifest
from deployment.runtime_refresh import (
    DeploymentUpdateHandoff,
    InstalledEntry,
    RefreshFailure,
    RefreshJournal,
    RefreshPolicy,
    attest_generation,
    attest_repository_boundary,
    build_generation,
    claim_pending,
    extract_tree_files,
    publish_activation_completions,
    refresh,
    rollback_switch,
)


def test_refresh_verifies_observation_with_anchor_observer_key() -> None:
    source = inspect.getsource(refresh)
    assert "/etc/traincapsule-verifier/anchor-observer-public-key.pem" in source
    assert "/etc/traincapsule-verifier/selector-public-key.pem" not in source


def _git(path: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments], cwd=path, check=True, capture_output=True, text=True
    ).stdout.strip()


def _fixture(tmp_path: Path) -> tuple[RefreshPolicy, DeploymentUpdateHandoff, Path, Path]:
    root = tmp_path / "root"
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-b", "main")
    _git(source, "config", "user.name", "Refresh Test")
    _git(source, "config", "user.email", "refresh@example.invalid")
    generation_id = "test-final-generation"
    source_raw = canonical_json_bytes({"generationId": generation_id})
    source_manifest_path = "docs/source-of-truth/test/FINAL_MANIFEST.json"
    files = {
        "config/active_generation.yaml": (
            b"schemaVersion: '3.1'\n"
            b"generationId: test-final-generation\n"
            b"sourceRoot: docs/source-of-truth/test\n"
            b"manifestPath: docs/source-of-truth/test/FINAL_MANIFEST.json\n"
        ),
        source_manifest_path: source_raw,
        "config/factory.yaml": b"schemaVersion: '3.1'\n",
        "tcfactory/__init__.py": b"VALUE = 1\n",
        "deployment/__init__.py": b"VALUE = 2\n",
        "verifier/src/traincapsule_verifier/__init__.py": b"VALUE = 3\n",
        "canary_runner/src/traincapsule_canary_runner/__init__.py": b"VALUE = 4\n",
        "packages/traincapsule-core/src/traincapsule_core/__init__.py": b"VALUE = 5\n",
        (
            "packages/traincapsule-ingest-pytorch/src/"
            "traincapsule_ingest_pytorch/__init__.py"
        ): b"VALUE = 6\n",
        "packages/traincapsule-qualify/src/traincapsule_qualify/__init__.py": (
            b"VALUE = 7\n"
        ),
        "packages/traincapsule-cli/src/traincapsule_cli/__init__.py": b"VALUE = 8\n",
        # A project hook is deliberately present.  The packager must treat it only as data.
        "setup.py": b"raise RuntimeError('PROJECT BUILD HOOK EXECUTED')\n",
        "uv.lock": b"offline-lock\n",
    }
    for relative, raw in files.items():
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    _git(source, "add", ".")
    _git(source, "commit", "-m", "candidate")
    main_sha = _git(source, "rev-parse", "HEAD")
    tree_sha = _git(source, "rev-parse", "HEAD^{tree}")
    bundle = tmp_path / "candidate.bundle"
    _git(source, "bundle", "create", str(bundle), "main")
    runtime = root / "opt/traincapsule-runtime/python/bin/python3.12"
    runtime.parent.mkdir(parents=True)
    runtime.write_text(f"#!/bin/sh\nexec {sys.executable} \"$@\"\n", encoding="utf-8")
    runtime.chmod(0o555)
    dependency = root / "etc/traincapsule-runtime/runtime.json"
    dependency.parent.mkdir(parents=True)
    dependency.write_bytes(canonical_json_bytes({"runtime": "test"}))
    dependency.chmod(0o444)
    lock = root / "opt/traincapsule-runtime/dependency.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_bytes(b"offline-lock\n")
    lock.chmod(0o444)
    policy = RefreshPolicy(
        proposal_root="/var/lib/traincapsule-runtime/deployment-update-handoffs",
        handoff_root="/var/lib/traincapsule-verifier/deployment-refresh-claims",
        evidence_root="/var/lib/traincapsule-verifier/anchor-updates",
        anchor_root="/var/lib/traincapsule-runtime/git",
        generation_root="/opt/traincapsule-runtime/generations",
        repository_boundary="/var/lib/traincapsule-verifier/repository-boundary",
        journal_root="/var/lib/traincapsule-verifier/deployment-refresh-journal",
        runtime_manifest_path="/etc/traincapsule-controller/runtime-manifest.json",
        environment_path="/etc/traincapsule-controller/controller-runtime.env",
        effective_config_path="/etc/traincapsule-controller/effective-config.yaml",
        generation_manifest_path="/etc/traincapsule-controller/deployment-generation.json",
        current_pointer="/opt/traincapsule-runtime/current",
        python_runtime="/opt/traincapsule-runtime/python/bin/python3.12",
        python_runtime_digest=sha256_digest(runtime.read_bytes()),
        dependency_manifest_path="/etc/traincapsule-runtime/runtime.json",
        dependency_manifest_digest=sha256_digest(dependency.read_bytes()),
        allowed_source_prefixes=(
            "tcfactory/",
            "deployment/",
            "verifier/src/traincapsule_verifier/",
            "canary_runner/src/traincapsule_canary_runner/",
            "packages/traincapsule-core/src/traincapsule_core/",
            "packages/traincapsule-ingest-pytorch/src/traincapsule_ingest_pytorch/",
            "packages/traincapsule-qualify/src/traincapsule_qualify/",
            "packages/traincapsule-cli/src/traincapsule_cli/",
        ),
        required_imports=(
            "tcfactory",
            "deployment",
            "traincapsule_verifier",
            "traincapsule_canary_runner",
            "traincapsule_core",
            "traincapsule_ingest_pytorch",
            "traincapsule_qualify",
            "traincapsule_cli",
        ),
        controller_unit="traincapsule-controller.service",
    )
    handoff = DeploymentUpdateHandoff(
        disposition="DEPLOYMENT_UPDATE_REQUIRED",
        installed_main_sha="0" * 40,
        installed_main_tree_sha="1" * 40,
        required_main_sha=main_sha,
        required_main_tree_sha=tree_sha,
        source_generation_id=generation_id,
        source_generation_digest=sha256_digest(source_raw),
        controller_runtime_may_execute_required_main=False,
        installed_runtime_attested=True,
        installed_runtime_manifest_digest="sha256:" + "2" * 64,
        next_action="INSTALL_SIGNED_SNAPSHOT_RUNTIME_AT_REQUIRED_MAIN",
    )
    return policy, handoff, bundle, root


def test_no_hook_generation_has_complete_inventory_and_fixed_import_origins(
    tmp_path: Path,
) -> None:
    policy, handoff, bundle, root = _fixture(tmp_path)
    generation, manifest, _ = build_generation(
        policy=policy,
        handoff=handoff,
        bundle=bundle,
        stage=tmp_path / "stage",
        root=root,
        authority_uid=os.getuid(),
    )
    assert set(manifest.import_origins) == set(policy.required_imports)
    assert all(
        origin == f"site-packages/{package}/__init__.py"
        for package, origin in manifest.import_origins.items()
    )
    assert not (generation / "site-packages/setup.py").exists()
    assert not (tmp_path / "PROJECT BUILD HOOK EXECUTED").exists()
    attest_generation(generation, manifest)
    snapshot = RepositorySnapshotManifest.model_validate_json(
        (generation / "repository/SNAPSHOT_MANIFEST.json").read_bytes(), strict=True
    )
    attest_repository_boundary(generation / "repository", snapshot)
    target = generation / manifest.import_origins["tcfactory"]
    target.chmod(0o644)
    target.write_bytes(b"substitution\n")
    with pytest.raises(RefreshFailure, match="generation entry changed"):
        attest_generation(generation, manifest)


def test_candidate_symlink_and_bundle_hardlink_are_rejected(tmp_path: Path) -> None:
    policy, handoff, bundle, _ = _fixture(tmp_path)
    linked = tmp_path / "linked.bundle"
    linked.hardlink_to(bundle)
    with pytest.raises(RefreshFailure, match="bundle file identity is unsafe"):
        extract_tree_files(
            linked,
            handoff.required_main_sha,
            handoff.required_main_tree_sha,
            tmp_path / "a",
        )
    source = tmp_path / "symlink-source"
    source.mkdir()
    _git(source, "init", "-b", "main")
    _git(source, "config", "user.name", "Refresh Test")
    _git(source, "config", "user.email", "refresh@example.invalid")
    (source / "escape.py").symlink_to("/home/jasim/escape.py")
    _git(source, "add", ".")
    _git(source, "commit", "-m", "symlink")
    sha = _git(source, "rev-parse", "HEAD")
    tree = _git(source, "rev-parse", "HEAD^{tree}")
    hostile = tmp_path / "hostile.bundle"
    _git(source, "bundle", "create", str(hostile), "main")
    with pytest.raises(RefreshFailure, match="symlink or special"):
        extract_tree_files(hostile, sha, tree, tmp_path / "b")
    with pytest.raises(ValueError, match="unsafe"):
        InstalledEntry(
            path="../escape.py",
            mode="0444",
            digest="sha256:" + "0" * 64,
            source_path="escape.py",
        )
    assert policy.python_runtime == "/opt/traincapsule-runtime/python/bin/python3.12"


def test_candidate_dependency_lock_cannot_change_offline_runtime(tmp_path: Path) -> None:
    policy, handoff, bundle, root = _fixture(tmp_path)
    installed_lock = root / "opt/traincapsule-runtime/dependency.lock"
    installed_lock.chmod(0o644)
    installed_lock.write_bytes(b"different-offline-lock\n")
    installed_lock.chmod(0o444)
    with pytest.raises(RefreshFailure, match="candidate dependency lock differs"):
        build_generation(
            policy=policy,
            handoff=handoff,
            bundle=bundle,
            stage=tmp_path / "stage",
            root=root,
            authority_uid=os.getuid(),
        )


def test_switching_rollback_restores_exact_state_and_is_idempotent(tmp_path: Path) -> None:
    policy, handoff, _, root = _fixture(tmp_path)
    boundary = root / policy.repository_boundary.lstrip("/")
    boundary.mkdir(parents=True)
    (boundary / "new").write_bytes(b"new")
    journal_root = root / policy.journal_root.lstrip("/")
    backup = journal_root / "backups/transaction"
    old_repository = backup / "repository-boundary"
    old_repository.mkdir(parents=True)
    (old_repository / "old").write_bytes(b"old")
    paths = {
        "previous_runtime_manifest": (
            "/etc/traincapsule-controller/runtime-manifest.json",
            b"old runtime\n",
        ),
        "previous_environment": (
            "/etc/traincapsule-controller/controller-runtime.env",
            b"old environment\n",
        ),
        "previous_effective_config": (
            "/etc/traincapsule-controller/effective-config.yaml",
            b"old config\n",
        ),
        "previous_generation_manifest": (
            "/etc/traincapsule-controller/deployment-generation.json",
            b"old generation\n",
        ),
    }
    backups: dict[str, str] = {}
    for field, (target_name, raw) in paths.items():
        target = root / target_name.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"new\n")
        saved = backup / target.name
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes(raw)
        backups[field] = str(saved)
    current = root / policy.current_pointer.lstrip("/")
    current.parent.mkdir(parents=True, exist_ok=True)
    os.symlink("/opt/traincapsule-runtime/generations/new", current)
    generation = root / "opt/traincapsule-runtime/generations/new"
    generation.mkdir(parents=True)
    journal = RefreshJournal(
        transaction_id="transaction",
        handoff_digest="sha256:" + "a" * 64,
        required_main_sha=handoff.required_main_sha,
        phase="SWITCHING",
        generation_path=str(generation),
        generation_created=True,
        repository_was_present=True,
        previous_pointer="/opt/traincapsule-runtime/generations/old",
        previous_repository=str(old_repository),
        previous_runtime_manifest=backups["previous_runtime_manifest"],
        previous_environment=backups["previous_environment"],
        previous_effective_config=backups["previous_effective_config"],
        previous_generation_manifest=backups["previous_generation_manifest"],
    )
    rollback_switch(policy, journal, root=root)
    rollback_switch(policy, journal, root=root)
    assert os.readlink(current) == "/opt/traincapsule-runtime/generations/old"
    assert (boundary / "old").read_bytes() == b"old"
    assert not generation.exists()
    for _field, (target_name, raw) in paths.items():
        assert (root / target_name.lstrip("/")).read_bytes() == raw


def test_claim_broker_copies_without_writing_controller_inbox(tmp_path: Path) -> None:
    policy, handoff, _, root = _fixture(tmp_path)
    proposal_root = root / policy.proposal_root.lstrip("/")
    proposal_root.mkdir(parents=True)
    raw = canonical_json_bytes(handoff)
    digest = sha256_digest(raw)
    proposal = proposal_root / f"{handoff.required_main_sha}-{digest[7:23]}.json"
    proposal.write_bytes(raw)
    proposal.chmod(0o600)
    claimed = claim_pending(
        policy,
        root=root,
        authority_uid=os.getuid(),
        controller_uid=os.getuid(),
    )
    assert proposal.read_bytes() == raw
    assert claimed == [root / policy.handoff_root.lstrip("/") / proposal.name]
    assert claimed[0].read_bytes() == raw
    assert claimed[0].stat().st_mode & 0o777 == 0o400


def test_systemd_units_separate_untrusted_claim_and_root_refresh_access() -> None:
    config = Path(__file__).resolve().parents[2] / "config"
    claim = (config / "traincapsule-deployment-refresh-claim.service").read_text()
    refresh = (config / "traincapsule-deployment-refresh.service").read_text()
    assert (
        "ReadOnlyPaths=/var/lib/traincapsule-runtime/deployment-update-handoffs" in claim
    )
    assert "ReadWritePaths=/var/lib/traincapsule-verifier/deployment-refresh-claims" in claim
    assert "ReadWritePaths=/var/lib/traincapsule-runtime" not in claim
    assert "ReadOnlyPaths=/var/lib/traincapsule-verifier/deployment-refresh-claims" in refresh
    assert "/deployment-update-handoffs" not in refresh
    assert "systemctl" not in refresh


def test_completion_broker_keeps_activation_claim_root_owned(tmp_path: Path) -> None:
    policy, handoff, _, root = _fixture(tmp_path)
    completion_root = root / policy.journal_root.lstrip("/") / "completions"
    completion_root.mkdir(parents=True)
    completion = {
        "schemaVersion": "3.1",
        "transactionId": "tx",
        "handoffDigest": "sha256:" + "a" * 64,
        "previousMainSha": handoff.installed_main_sha,
        "requiredMainSha": handoff.required_main_sha,
        "requiredMainTreeSha": handoff.required_main_tree_sha,
        "sourceGenerationId": handoff.source_generation_id,
        "sourceGenerationDigest": handoff.source_generation_digest,
        "generationManifestDigest": "sha256:" + "b" * 64,
        "runtimeManifestDigest": "sha256:" + "c" * 64,
        "environmentDigest": "sha256:" + "d" * 64,
        "effectiveConfigDigest": "sha256:" + "e" * 64,
        "snapshotManifestDigest": "sha256:" + "f" * 64,
        "committedAt": "2026-08-12T20:00:00Z",
    }
    source = completion_root / f"{handoff.required_main_sha}-tx.json"
    source.write_bytes(canonical_json_bytes(completion))
    source.chmod(0o400)
    published = publish_activation_completions(
        policy,
        root=root,
        authority_uid=os.getuid(),
        controller_uid=os.getuid(),
    )
    assert len(published) == 1
    assert published[0].stat().st_uid == os.getuid()
    assert published[0].stat().st_mode & 0o777 == 0o440
    retirement = (
        root
        / "var/lib/traincapsule-verifier/activation-refresh-retirement/retired"
    )
    retirement.mkdir(parents=True)
    retired = retirement / source.name
    retired.write_bytes(source.read_bytes())
    retired.chmod(0o440)
    published[0].unlink()
    assert (
        publish_activation_completions(
            policy,
            root=root,
            authority_uid=os.getuid(),
            controller_uid=os.getuid(),
        )
        == []
    )
    assert not published[0].exists()
