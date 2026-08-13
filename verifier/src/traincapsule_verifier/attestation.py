"""Truthful external verifier installation rehearsal and attestation."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

from pydantic import BaseModel, ValidationError

from .canonical import model_digest
from .crypto import (
    SignatureError,
    load_private_key,
    load_public_key,
    public_key_fingerprint,
    verify_model_signature,
)
from .filesystem import (
    TrustedRoot,
    open_trusted_file,
    open_trusted_root,
    read_bounded_file,
    sha256_file,
    strict_json_loads,
)
from .models import (
    AuthorityAnchor,
    InstallationAttestation,
    InstallationState,
    RevocationList,
    VerifierPolicy,
)


class InstallationError(RuntimeError):
    pass


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise InstallationError("distribution cannot contain symbolic links")
        if path.is_file():
            relative = path.relative_to(root).as_posix().encode()
            digest.update(len(relative).to_bytes(8, "big"))
            digest.update(relative)
            data = path.read_bytes()
            digest.update(len(data).to_bytes(8, "big"))
            digest.update(data)
    return "sha256:" + digest.hexdigest()


def _load[T: BaseModel](root: TrustedRoot, relative: str, model: type[T]) -> T:
    raw = read_bounded_file(root, relative)
    strict_json_loads(raw)
    try:
        return model.model_validate_json(raw)
    except (ValidationError, ValueError) as exc:
        raise InstallationError(f"installed {relative} is invalid") from exc


def attest_installation(
    installation_root: Path,
    *,
    distribution_root: Path,
    expected_owner_uid: int,
) -> InstallationAttestation:
    if installation_root.is_symlink():
        raise InstallationError("installation root cannot be a symbolic link")
    root = installation_root.resolve(strict=True)
    expected = {
        "etc": root / "etc/traincapsule-verifier",
        "state": root / "var/lib/traincapsule-verifier",
        "private": root / "var/lib/traincapsule-verifier/private",
        "receipts": root / "var/lib/traincapsule-verifier/receipts",
        "oracle": root / "var/lib/traincapsule-verifier/oracle",
        "logs": root / "var/log/traincapsule-verifier",
    }
    checked: dict[str, str] = {}
    roots: dict[str, TrustedRoot] = {}
    try:
        for label, path in expected.items():
            try:
                trusted = open_trusted_root(path, expected_uid=expected_owner_uid)
            except (OSError, ValueError) as exc:
                raise InstallationError(f"{label} trust root is invalid") from exc
            roots[label] = trusted
            metadata = os.fstat(trusted.descriptor)
            checked[label] = oct(stat.S_IMODE(metadata.st_mode))
        return _attest_opened_roots(
            installation_root=root,
            distribution_root=distribution_root,
            expected_owner_uid=expected_owner_uid,
            roots=roots,
            checked=checked,
        )
    finally:
        for trusted in reversed(tuple(roots.values())):
            trusted.close()


def _attest_opened_roots(
    *,
    installation_root: Path,
    distribution_root: Path,
    expected_owner_uid: int,
    roots: dict[str, TrustedRoot],
    checked: dict[str, str],
) -> InstallationAttestation:

    public_key = load_public_key(
        read_bounded_file(roots["etc"], "public-key.pem", maximum_bytes=8192)
    )
    required = {
        "policy.json": (roots["etc"], "policy.json"),
        "private/signing-key.pem": (roots["private"], "signing-key.pem"),
        "revocations.json": (roots["state"], "revocations.json"),
        "authority-anchor.json": (roots["state"], "authority-anchor.json"),
    }
    missing: list[str] = []
    for name, (trusted_root, relative) in required.items():
        try:
            read_bounded_file(
                trusted_root,
                relative,
                maximum_bytes=8192 if relative.endswith(".pem") else 10_000_000,
                required_mode=0o600 if relative == "signing-key.pem" else None,
            )
        except FileNotFoundError:
            missing.append(name)
        except (OSError, ValueError) as exc:
            raise InstallationError(f"installed {name} is not trusted") from exc

    authority_validated = False
    if not missing:
        policy = _load(roots["etc"], "policy.json", VerifierPolicy)
        revocations = _load(roots["state"], "revocations.json", RevocationList)
        anchor = _load(roots["state"], "authority-anchor.json", AuthorityAnchor)
        signing_key = load_private_key(
            read_bounded_file(
                roots["private"],
                "signing-key.pem",
                maximum_bytes=8192,
                required_mode=0o600,
            )
        )
        fingerprint = public_key_fingerprint(public_key)
        if fingerprint != public_key_fingerprint(signing_key.public_key()):
            raise InstallationError("installed public and private keys do not match")
        if fingerprint != policy.public_key_fingerprint:
            raise InstallationError("installed policy does not pin the public key")
        try:
            verify_model_signature(revocations, public_key)
        except SignatureError as exc:
            raise InstallationError("installed revocation signature is invalid") from exc
        authority_values = (
            (revocations.policy_id, policy.policy_id),
            (revocations.policy_version, policy.policy_version),
            (revocations.issuer_id, policy.issuer_id),
            (revocations.issuer_key_id, policy.issuer_key_id),
            (anchor.policy_id, policy.policy_id),
            (anchor.policy_version, policy.policy_version),
            (anchor.issuer_id, policy.issuer_id),
            (anchor.issuer_key_id, policy.issuer_key_id),
            (anchor.public_key_fingerprint, fingerprint),
            (anchor.revocation_epoch, revocations.revocation_epoch),
            (anchor.revocation_list_digest, model_digest(revocations)),
            (anchor.previous_revocation_list_digest, revocations.previous_list_digest),
        )
        if any(observed != expected_value for observed, expected_value in authority_values):
            raise InstallationError("installed authority chain is inconsistent")
        if revocations.revocation_epoch < policy.minimum_revocation_epoch:
            raise InstallationError("installed revocation epoch is below policy minimum")
        for risk in policy.risk_policies.values():
            for identifier, path in risk.oracle_runner_paths.items():
                descriptor = open_trusted_file(
                    roots["oracle"], path, maximum_bytes=5_000_000, require_executable=True
                )
                os.close(descriptor)
                if sha256_file(roots["oracle"], path) != risk.oracle_runner_digests[identifier]:
                    raise InstallationError("installed oracle runner digest mismatch")
        authority_validated = True

    missing.extend(["live-oracle-verification", "live-service-verification"])
    return InstallationAttestation(
        schema_version="3.1",
        installation_root=str(installation_root),
        verifier_distribution_digest=_tree_digest(distribution_root),
        public_key_fingerprint=public_key_fingerprint(public_key),
        expected_owner_uid=expected_owner_uid,
        checked_paths=checked,
        missing_private_inputs=missing,
        authority_validated=authority_validated,
        live_oracle_verified=False,
        live_service_verified=False,
        state=InstallationState.STAGED_NOT_ACTIVATED,
    )


def rehearse_layout(destination: Path, public_key_pem: bytes) -> Path:
    """Create a disposable, inactive filesystem layout; never install a private key."""

    if destination.exists():
        raise InstallationError("rehearsal destination already exists")
    paths = (
        destination / "etc/traincapsule-verifier",
        destination / "var/lib/traincapsule-verifier/private",
        destination / "var/lib/traincapsule-verifier/receipts",
        destination / "var/lib/traincapsule-verifier/oracle",
        destination / "var/log/traincapsule-verifier",
    )
    for path in paths:
        path.mkdir(parents=True, mode=0o700)
        path.chmod(0o700)
    public_key = destination / "etc/traincapsule-verifier/public-key.pem"
    public_key.write_bytes(public_key_pem)
    public_key.chmod(0o400)
    marker = destination / "STAGED_NOT_ACTIVATED"
    marker.write_text(
        "Install private policy, revocation state, authority anchor, oracle data, signing key, "
        "and credentials through the external verifier authority before activation.\n",
        encoding="utf-8",
    )
    marker.chmod(0o400)
    return destination
