"""Strict off-repository Phase 6 installation loader.

The controller may consume this configuration, but cannot author it: every
input lives below a root-owned installation root and the mutable CAS/journal
roots live below a separately owned service-data root.
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

import yaml
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import Field, ValidationError, field_validator, model_validator

from tcfactory.util import run_command, sanitized_subprocess_env, sha256_file
from tcfactory.v3.base import DIGEST_PATTERN, V3Model
from tcfactory.v3.contracts_v31 import MachinePolicyReceiptV31
from tcfactory.v3.external_actions import (
    ExternalActionAdapter,
    ExternalActionBackend,
    ExternalActionChannel,
    ExternalActionInstallation,
    ExternalActionJournal,
    ExternalActionPayload,
    ExternalActionPolicyError,
    ExternalDeliveryReceipt,
    ExternalPolicyArtifactVerifier,
    MachinePolicyReceiptVerifier,
)
from tcfactory.v3.phase6_runtime import (
    Phase6ControllerRuntime,
    ResearchOutputDeclaration,
    ResearchOutputKind,
)
from tcfactory.v3.publication import PublicCheckAuthorization
from tcfactory.v3.service_storage import ServiceStorageError, TrustedServiceDirectory
from tcfactory.v3.source_acquisition import (
    BoundedJsonClaimParser,
    ControlledSourceAcquirer,
    ReceiptAuthority,
    ResearchControl,
    ResearchControlOracle,
    ResearchQueryPlan,
    SourceAcquisitionError,
    SourceAcquisitionPolicy,
    SourceArtifact,
    SourceParserRegistry,
    research_artifact_roster_digest,
    research_control_result_digest,
)
from tcfactory.v3.work_items import WorkItemCollection

PHASE6_INSTALL_ROOT = Path("/etc/traincapsule-factory/phase6")
PHASE6_SERVICE_ROOT = Path("/var/lib/traincapsule-factory/phase6")
REQUIRED_RESEARCH_OUTPUTS: dict[str, frozenset[ResearchOutputKind]] = {
    "V3-MKT-001": frozenset({ResearchOutputKind.REACHABLE_ACCOUNT_MAP}),
    "V3-MKT-002": frozenset(
        {
            ResearchOutputKind.DISCOVERY_INTERVIEW_GUIDE,
            ResearchOutputKind.PILOT_QUALIFICATION_RUBRIC,
        }
    ),
}


class Phase6InstallationError(RuntimeError):
    """The installed Phase 6 authority boundary is incomplete or unsafe."""


class InstalledFile(V3Model):
    path: Path
    digest: str = Field(pattern=DIGEST_PATTERN.pattern)

    @field_validator("path")
    @classmethod
    def absolute_path(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("installed paths must be absolute")
        return value


class ResearchItemInstallation(V3Model):
    plan: InstalledFile
    controls: InstalledFile
    outputs: tuple[ResearchOutputDeclaration, ...] = ()

    @model_validator(mode="after")
    def unique_outputs(self) -> ResearchItemInstallation:
        if len({value.kind for value in self.outputs}) != len(self.outputs):
            raise ValueError("research output kinds must be unique per work item")
        return self


class ExternalActionItemInstallation(V3Model):
    request: InstalledFile


class Phase6InstallationManifest(V3Model):
    schema_version: Literal["3.1"]
    installation_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    service_owner_uid: int = Field(ge=1)
    research_policy: InstalledFile
    source_receipt_authority_executable: InstalledFile
    research_control_oracle_executable: InstalledFile
    source_receipt_issuer_id: str = Field(min_length=1, max_length=128)
    source_receipt_key_id: str = Field(min_length=1, max_length=128)
    research_cas_root: Path
    research_items: dict[str, ResearchItemInstallation]
    external_action_installation: InstalledFile
    external_machine_receipt: InstalledFile
    external_legal_policy: InstalledFile
    external_safety_policy: InstalledFile
    external_public_verifier_executable: InstalledFile
    external_backend_executable: InstalledFile
    external_action_items: dict[str, ExternalActionItemInstallation]
    external_journal_root: Path
    external_outcome_root: Path

    @field_validator(
        "research_cas_root", "external_journal_root", "external_outcome_root"
    )
    @classmethod
    def absolute_data_root(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("service data roots must be absolute")
        return value


def _canonical_json(raw: bytes) -> object:
    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values:
            if key in result:
                raise ValueError("duplicate JSON member")
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=pairs)


def _trusted_path(
    path: Path,
    *,
    owner_uid: int,
    directory: bool,
    label: str,
    writable: bool = False,
) -> Path:
    absolute = Path(os.path.abspath(path))
    try:
        resolved = absolute.resolve(strict=True)
    except OSError as exc:
        raise Phase6InstallationError(f"{label} is unavailable") from exc
    if resolved != absolute:
        raise Phase6InstallationError(f"{label} or an ancestor is a symlink")
    observed = resolved.lstat()
    correct_type = stat.S_ISDIR(observed.st_mode) if directory else stat.S_ISREG(
        observed.st_mode
    )
    if not correct_type or observed.st_uid != owner_uid:
        raise Phase6InstallationError(f"{label} has the wrong type or owner")
    if writable and stat.S_IMODE(observed.st_mode) != 0o700:
        raise Phase6InstallationError(f"{label} must have exact owner-only mode 0700")
    if not writable and observed.st_mode & 0o022:
        raise Phase6InstallationError(f"{label} is group/world writable")
    for ancestor in resolved.parents:
        metadata = ancestor.lstat()
        if metadata.st_mode & 0o002 and not metadata.st_mode & stat.S_ISVTX:
            raise Phase6InstallationError(f"{label} has a world-writable ancestor")
    return resolved


def _under(path: Path, root: Path, *, label: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise Phase6InstallationError(f"{label} escapes its installed root") from exc


def _verify_digest(path: Path, expected: str, *, label: str) -> None:
    observed = f"sha256:{sha256_file(path)}"
    if observed != expected:
        raise Phase6InstallationError(f"{label} digest mismatch")


class ExecutableSourceReceiptAuthority(ReceiptAuthority):
    signature_algorithm = "ed25519"

    def __init__(self, executable: Path, *, issuer_id: str, key_id: str) -> None:
        self.executable = executable
        self.issuer_id = issuer_id
        self.key_id = key_id

    def _invoke(self, operation: str, payload: bytes, signature: str | None = None) -> str:
        arguments = [
            str(self.executable),
            operation,
            "--issuer-id",
            self.issuer_id,
            "--key-id",
            self.key_id,
            "--algorithm",
            self.signature_algorithm,
        ]
        if signature is not None:
            arguments.extend(["--signature", signature])
        result = run_command(
            arguments,
            cwd=self.executable.parent,
            check=False,
            timeout=30,
            env=sanitized_subprocess_env(),
            input_text=payload.decode("utf-8", errors="strict"),
        )
        if result.returncode != 0:
            raise Phase6InstallationError("external source receipt authority rejected request")
        return result.stdout.strip()

    def sign(self, payload: bytes) -> str:
        signature = self._invoke("sign", payload)
        if len(signature) != 128:
            raise Phase6InstallationError("source receipt signature has the wrong shape")
        bytes.fromhex(signature)
        return signature

    def verify(
        self,
        payload: bytes,
        *,
        signature: str,
        issuer_id: str,
        key_id: str,
        signature_algorithm: str,
    ) -> bool:
        if (
            issuer_id != self.issuer_id
            or key_id != self.key_id
            or signature_algorithm != self.signature_algorithm
        ):
            return False
        try:
            self._invoke("verify", payload, signature)
        except (OSError, Phase6InstallationError, UnicodeDecodeError, ValueError):
            return False
        return True


class ExecutableResearchControlOracle(ResearchControlOracle):
    """Execute a content-pinned external oracle over the exact raw artifact roster."""

    def __init__(self, executable: Path, executable_digest: str) -> None:
        self.executable = executable
        self.executable_digest = executable_digest

    def evaluate(
        self,
        *,
        plan: ResearchQueryPlan,
        artifact_root: Path,
        artifacts: list[SourceArtifact],
        expected_controls: list[ResearchControl],
        artifact_root_opener: Callable[[], int] | None,
    ) -> list[ResearchControl]:
        del artifact_root
        if artifact_root_opener is None:
            raise SourceAcquisitionError("control oracle requires a trusted CAS opener")
        try:
            root_fd = artifact_root_opener()
        except Exception as exc:
            raise SourceAcquisitionError("control oracle CAS identity changed") from exc
        try:
            raw_bindings: list[dict[str, str]] = []
            for artifact in sorted(artifacts, key=lambda value: value.source_id):
                fd = os.open(
                    artifact.artifact_path,
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=root_fd,
                )
                try:
                    metadata = os.fstat(fd)
                    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 16 * 1024 * 1024:
                        raise SourceAcquisitionError("control oracle raw evidence is unsafe")
                    raw = b""
                    while len(raw) <= 16 * 1024 * 1024:
                        chunk = os.read(fd, min(65_536, 16 * 1024 * 1024 + 1 - len(raw)))
                        if not chunk:
                            break
                        raw += chunk
                finally:
                    os.close(fd)
                digest = "sha256:" + __import__("hashlib").sha256(raw).hexdigest()
                if digest != artifact.content_digest:
                    raise SourceAcquisitionError("control oracle raw digest mismatch")
                raw_bindings.append(
                    {
                        "sourceId": artifact.source_id,
                        "artifactDigest": digest,
                        "rawHex": raw.hex(),
                    }
                )
        finally:
            os.close(root_fd)
        request = {
            "schemaVersion": "3.1",
            "planDigest": "sha256:"
            + __import__("hashlib").sha256(plan.canonical_json_bytes()).hexdigest(),
            "artifacts": raw_bindings,
            "rawArtifactRosterDigest": research_artifact_roster_digest(artifacts),
            "oracleExecutableDigest": self.executable_digest,
            "expectedControls": [
                {
                    "kind": control.kind.value,
                    "expectedVerdict": control.expected_verdict.value,
                }
                for control in expected_controls
            ],
        }
        oracle_digest = f"sha256:{sha256_file(self.executable)}"
        if oracle_digest != self.executable_digest:
            raise SourceAcquisitionError("research control oracle executable changed")
        result = run_command(
            [str(self.executable), "evaluate-controls"],
            cwd=self.executable.parent,
            check=False,
            timeout=30,
            env=sanitized_subprocess_env(),
            input_text=json.dumps(request, sort_keys=True, separators=(",", ":")),
        )
        if result.returncode != 0 or len(result.stdout.encode()) > 65_536:
            raise SourceAcquisitionError("research control oracle rejected bound evidence")
        try:
            raw_result = _canonical_json(result.stdout.encode())
            if not isinstance(raw_result, list):
                raise ValueError("oracle response is not a list")
            values = cast(list[object], raw_result)
            computed: list[ResearchControl] = []
            for raw_value in values:
                computed.append(ResearchControl.model_validate(raw_value, strict=False))
        except (TypeError, ValueError, ValidationError) as exc:
            raise SourceAcquisitionError("research control oracle response is invalid") from exc
        if len(computed) != len(expected_controls):
            raise SourceAcquisitionError("research control oracle roster mismatch")
        expected = {(value.kind, value.expected_verdict) for value in expected_controls}
        observed = {(value.kind, value.observed_verdict) for value in computed}
        roster_digest = research_artifact_roster_digest(artifacts)
        if observed != expected or any(
            value.artifact_digest != roster_digest
            or value.raw_artifact_roster_digest != roster_digest
            or value.oracle_executable_digest != oracle_digest
            or value.oracle_result_digest != research_control_result_digest(computed)
            for value in computed
        ):
            raise SourceAcquisitionError("research control oracle changed preregistered controls")
        return computed


class PublicExternalActionReceiptVerifier(MachinePolicyReceiptVerifier):
    def __init__(self, executable: Path, receipt_path: Path) -> None:
        self.executable = executable
        self.receipt_path = receipt_path

    def verify(self, receipt: MachinePolicyReceiptV31, *, now: datetime) -> str:
        try:
            raw = self.receipt_path.read_bytes()
            _canonical_json(raw)
            installed = MachinePolicyReceiptV31.model_validate_json(
                raw, strict=True
            )
        except (OSError, ValueError, ValidationError) as exc:
            raise ExternalActionPolicyError("installed machine receipt is invalid") from exc
        if installed != receipt or receipt.expires_at <= now:
            raise ExternalActionPolicyError("installed machine receipt binding mismatch")
        result = run_command(
            [
                str(self.executable),
                "verify-receipt",
                "--receipt",
                str(self.receipt_path),
                "--candidate-sha",
                receipt.candidate_sha,
                "--candidate-tree-sha",
                receipt.candidate_tree_sha,
                "--base-sha",
                receipt.base_sha,
                "--work-item-id",
                receipt.work_item_id,
                "--candidate-manifest-digest",
                receipt.candidate_manifest_digest,
            ],
            cwd=self.executable.parent,
            check=False,
            timeout=60,
            env=sanitized_subprocess_env(),
        )
        if result.returncode != 0 or len(result.stdout.encode()) > 65_536:
            raise ExternalActionPolicyError("public verifier rejected machine receipt")
        try:
            authorization = PublicCheckAuthorization.model_validate_json(
                result.stdout, strict=True
            )
        except ValueError as exc:
            raise ExternalActionPolicyError("public verifier output is invalid") from exc
        digest = receipt.canonical_digest()
        if (
            authorization.receipt_id != receipt.receipt_id
            or authorization.receipt_digest != digest
            or authorization.candidate_sha != receipt.candidate_sha
        ):
            raise ExternalActionPolicyError("public verifier output is not exact")
        return digest


class InstalledPolicyVerifier(ExternalPolicyArtifactVerifier):
    def __init__(self, policies: dict[str, tuple[Path, str]]) -> None:
        self.policies = policies

    def verify(self, *, policy_id: str, policy_digest: str) -> bool:
        installed = self.policies.get(policy_id)
        return bool(
            installed
            and installed[1] == policy_digest
            and f"sha256:{sha256_file(installed[0])}" == policy_digest
        )


class InstalledExternalActionBackend(ExternalActionBackend):
    def __init__(self, executable: Path, backend_id: str) -> None:
        self.executable = executable
        self.backend_id = backend_id

    def is_available(
        self, *, channel: ExternalActionChannel, credential_reference: str
    ) -> bool:
        result = run_command(
            [
                str(self.executable),
                "available",
                "--channel",
                channel.value,
                "--credential-reference",
                credential_reference,
            ],
            cwd=self.executable.parent,
            check=False,
            timeout=30,
            env=sanitized_subprocess_env(),
        )
        return result.returncode == 0

    def send(self, payload: ExternalActionPayload) -> ExternalDeliveryReceipt:
        result = run_command(
            [str(self.executable), "send"],
            cwd=self.executable.parent,
            check=False,
            timeout=60,
            env=sanitized_subprocess_env(),
            input_text=payload.canonical_json_bytes().decode("utf-8"),
        )
        if result.returncode != 0 or len(result.stdout.encode()) > 65_536:
            raise ExternalActionPolicyError("installed external action backend failed")
        return ExternalDeliveryReceipt.model_validate_json(result.stdout, strict=True)


def _load_manifest(
    install_root: Path, *, expected_root_uid: int
) -> Phase6InstallationManifest:
    root = _trusted_path(
        install_root,
        owner_uid=expected_root_uid,
        directory=True,
        label="Phase 6 installation root",
    )
    manifest_path = _trusted_path(
        root / "installation.json",
        owner_uid=expected_root_uid,
        directory=False,
        label="Phase 6 installation manifest",
    )
    signature_path = _trusted_path(
        root / "installation.json.sig",
        owner_uid=expected_root_uid,
        directory=False,
        label="Phase 6 manifest signature",
    )
    key_path = _trusted_path(
        root / "manifest-public-key.pem",
        owner_uid=expected_root_uid,
        directory=False,
        label="Phase 6 manifest public key",
    )
    raw = manifest_path.read_bytes()
    try:
        _canonical_json(raw)
        manifest = Phase6InstallationManifest.model_validate_json(raw, strict=True)
        if raw != manifest.canonical_json_bytes():
            raise Phase6InstallationError("Phase 6 manifest bytes are not canonical")
        key = serialization.load_pem_public_key(key_path.read_bytes())
        if not isinstance(key, Ed25519PublicKey):
            raise Phase6InstallationError("Phase 6 manifest key is not Ed25519")
        key.verify(bytes.fromhex(signature_path.read_text().strip()), raw)
    except (InvalidSignature, ValueError, ValidationError) as exc:
        raise Phase6InstallationError("Phase 6 manifest signature or shape is invalid") from exc
    return manifest


def load_phase6_runtime(
    *,
    repo_root: Path,
    install_root: Path = PHASE6_INSTALL_ROOT,
    service_root: Path = PHASE6_SERVICE_ROOT,
    expected_root_uid: int = 0,
) -> Phase6ControllerRuntime:
    """Load the strict installation; raise on every ambiguous boundary."""

    manifest = _load_manifest(install_root, expected_root_uid=expected_root_uid)
    install = install_root.resolve(strict=True)
    service = _trusted_path(
        service_root,
        owner_uid=manifest.service_owner_uid,
        directory=True,
        label="Phase 6 service root",
        writable=True,
    )
    try:
        service_guard = TrustedServiceDirectory.capture(
            service, owner_uid=manifest.service_owner_uid
        )
    except ServiceStorageError as exc:
        raise Phase6InstallationError("Phase 6 service root identity is unsafe") from exc

    def installed_file(value: InstalledFile, label: str) -> Path:
        path = _trusted_path(
            value.path,
            owner_uid=expected_root_uid,
            directory=False,
            label=label,
        )
        _under(path, install, label=label)
        _verify_digest(path, value.digest, label=label)
        return path

    research_policy_path = installed_file(manifest.research_policy, "research policy")
    try:
        policy_raw = research_policy_path.read_bytes()
        _canonical_json(policy_raw)
        policy = SourceAcquisitionPolicy.model_validate_json(policy_raw, strict=True)
    except (ValueError, ValidationError) as exc:
        raise Phase6InstallationError("research policy is invalid") from exc
    authority_executable = installed_file(
        manifest.source_receipt_authority_executable,
        "source receipt authority executable",
    )
    control_oracle_executable = installed_file(
        manifest.research_control_oracle_executable,
        "research control oracle executable",
    )
    if not os.access(authority_executable, os.X_OK) or not os.access(
        control_oracle_executable, os.X_OK
    ):
        raise Phase6InstallationError("source receipt authority/control oracle is not executable")
    cas_root = _trusted_path(
        manifest.research_cas_root,
        owner_uid=manifest.service_owner_uid,
        directory=True,
        label="research CAS root",
        writable=True,
    )
    _under(cas_root, service, label="research CAS root")
    cas_guard = TrustedServiceDirectory.capture(
        cas_root, owner_uid=manifest.service_owner_uid
    )
    roadmap = WorkItemCollection.model_validate(
        cast(
            object,
            yaml.safe_load(
                (repo_root / "factory/roadmap/work_items.yaml").read_text(encoding="utf-8")
            ),
        )
    )
    research_ids = {
        item.work_item_id
        for item in roadmap.work_items
        if item.kind.value == "RESEARCH" and item.lane.value in {"MARKET", "COMPETITOR"}
    }
    if set(manifest.research_items) != research_ids:
        raise Phase6InstallationError("installation does not cover every active research item")
    declarations: dict[str, tuple[ResearchOutputDeclaration, ...]] = {}
    plan_root: Path | None = None
    for work_item_id, item_install in manifest.research_items.items():
        plan = installed_file(item_install.plan, f"{work_item_id} research plan")
        controls = installed_file(item_install.controls, f"{work_item_id} research controls")
        expected_plan = plan.parent / f"{work_item_id}.json"
        expected_controls = plan.parent / f"{work_item_id}.controls.json"
        if plan != expected_plan or controls != expected_controls:
            raise Phase6InstallationError("research records do not use exact installed names")
        if plan_root is None:
            plan_root = plan.parent
        elif plan.parent != plan_root:
            raise Phase6InstallationError("research records do not share one trusted root")
        for output in item_install.outputs:
            record = plan.parent / f"{work_item_id}{output.record_suffix}"
            installed_file(
                InstalledFile(path=record, digest=output.record_digest),
                f"{work_item_id} typed research output",
            )
        declarations[work_item_id] = item_install.outputs
        required_outputs = REQUIRED_RESEARCH_OUTPUTS.get(work_item_id, frozenset())
        if {value.kind for value in item_install.outputs} != set(required_outputs):
            raise Phase6InstallationError(
                f"{work_item_id} does not declare its exact typed research outputs"
            )
    if plan_root is None:
        raise Phase6InstallationError("installation contains no research plan root")

    action_install_path = installed_file(
        manifest.external_action_installation, "external action installation"
    )
    try:
        action_install_raw = action_install_path.read_bytes()
        _canonical_json(action_install_raw)
        action_install = ExternalActionInstallation.model_validate_json(
            action_install_raw, strict=True
        )
    except (ValueError, ValidationError) as exc:
        raise Phase6InstallationError("external action installation is invalid") from exc
    receipt_path = installed_file(
        manifest.external_machine_receipt, "external machine receipt"
    )
    try:
        receipt_raw = receipt_path.read_bytes()
        _canonical_json(receipt_raw)
        receipt = MachinePolicyReceiptV31.model_validate_json(receipt_raw, strict=True)
    except (ValueError, ValidationError) as exc:
        raise Phase6InstallationError("external machine receipt is invalid") from exc
    if receipt != action_install.machine_policy_receipt:
        raise Phase6InstallationError("external action installation receipt mismatch")
    legal_path = installed_file(manifest.external_legal_policy, "external legal policy")
    safety_path = installed_file(manifest.external_safety_policy, "external safety policy")
    verifier_executable = installed_file(
        manifest.external_public_verifier_executable, "public verifier executable"
    )
    backend_executable = installed_file(
        manifest.external_backend_executable, "external action backend executable"
    )
    if not os.access(verifier_executable, os.X_OK) or not os.access(
        backend_executable, os.X_OK
    ):
        raise Phase6InstallationError("installed Phase 6 executables are not executable")
    journal_root = _trusted_path(
        manifest.external_journal_root,
        owner_uid=manifest.service_owner_uid,
        directory=True,
        label="external action journal root",
        writable=True,
    )
    outcome_root = _trusted_path(
        manifest.external_outcome_root,
        owner_uid=manifest.service_owner_uid,
        directory=True,
        label="external action outcome root",
        writable=True,
    )
    _under(journal_root, service, label="external action journal root")
    _under(outcome_root, service, label="external action outcome root")
    journal_guard = TrustedServiceDirectory.capture(
        journal_root, owner_uid=manifest.service_owner_uid
    )
    outcome_guard = TrustedServiceDirectory.capture(
        outcome_root, owner_uid=manifest.service_owner_uid
    )
    os.close(service_guard.open_fd())
    action_ids = set(manifest.external_action_items)
    roadmap_by_id = {item.work_item_id: item for item in roadmap.work_items}
    for work_item_id, action in manifest.external_action_items.items():
        roadmap_item = roadmap_by_id.get(work_item_id)
        if roadmap_item is None or roadmap_item.kind.value not in {
            "COMMERCIAL_EXPERIMENT",
            "EXTERNAL_EVIDENCE",
        }:
            raise Phase6InstallationError("external action item is not an authorized roadmap row")
        request = installed_file(action.request, f"{work_item_id} external action request")
        if request.name != f"{work_item_id}.json":
            raise Phase6InstallationError("external action request name mismatch")
    request_roots = {value.request.path.parent for value in manifest.external_action_items.values()}
    if len(request_roots) != 1:
        raise Phase6InstallationError("external action requests do not share one trusted root")
    request_root = next(iter(request_roots))

    authority = ExecutableSourceReceiptAuthority(
        authority_executable,
        issuer_id=manifest.source_receipt_issuer_id,
        key_id=manifest.source_receipt_key_id,
    )
    action_adapter = ExternalActionAdapter(
        installation=action_install,
        verifier=PublicExternalActionReceiptVerifier(verifier_executable, receipt_path),
        policy_verifier=InstalledPolicyVerifier(
            {
                action_install.legal_policy_id: (
                    legal_path,
                    action_install.legal_policy_digest,
                ),
                action_install.safety_policy_id: (
                    safety_path,
                    action_install.safety_policy_digest,
                ),
            }
        ),
        backend=InstalledExternalActionBackend(
            backend_executable, action_install.backend_id
        ),
        journal=ExternalActionJournal(journal_root, root_opener=journal_guard),
    )
    return Phase6ControllerRuntime(
        research_plan_root=plan_root,
        research_acquirer=ControlledSourceAcquirer(
            policy=policy,
            artifact_root=cas_root,
            receipt_authority=authority,
            artifact_root_opener=cas_guard.open_fd,
        ),
        parser_registry=SourceParserRegistry([BoundedJsonClaimParser()]),
        source_receipt_authority=authority,
        research_control_oracle=ExecutableResearchControlOracle(
            control_oracle_executable,
            manifest.research_control_oracle_executable.digest,
        ),
        external_request_root=request_root,
        external_action_adapter=action_adapter,
        external_outcome_root=outcome_root,
        external_outcome_guard=outcome_guard,
        research_output_declarations=declarations,
        external_action_item_ids=frozenset(action_ids),
        trusted_input_owner_uid=expected_root_uid,
    )


def build_phase6_runtime(*, repo_root: Path) -> Phase6ControllerRuntime:
    """Production CLI seam: unsafe/missing Phase 6 installs wait item-locally."""

    try:
        return load_phase6_runtime(
            repo_root=repo_root,
            install_root=PHASE6_INSTALL_ROOT,
            service_root=PHASE6_SERVICE_ROOT,
        )
    except (OSError, Phase6InstallationError, ValidationError, ValueError):
        return Phase6ControllerRuntime.unavailable()
