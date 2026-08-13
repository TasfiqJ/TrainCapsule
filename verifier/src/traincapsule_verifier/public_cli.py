"""Unprivileged public verification CLI; no issuing capability is reachable here."""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

from .canonical import canonical_json_bytes
from .models import ActivationReceipt, MachinePolicyReceipt, RulesetObservationReceipt
from .public_crypto import load_public_key, verify_model_signature
from .public_verifier import (
    PublicVerificationError,
    PublicVerifier,
    parse_receipt,
    validate_root_owned_ancestry,
)

CONFIG_ROOT = Path("/etc/traincapsule-verifier")
STATE_ROOT = Path("/var/lib/traincapsule-verifier")
RECEIPT_ROOT = STATE_ROOT / "receipts"
EXPECTED_OWNER_UID = 0


@dataclass(slots=True)
class PublicExecutableIdentity:
    path: Path
    descriptor: int
    device: int
    inode: int

    def revalidate(self) -> None:
        observed = os.stat(self.path, follow_symlinks=False)
        if not stat.S_ISREG(observed.st_mode) or (observed.st_dev, observed.st_ino) != (
            self.device,
            self.inode,
        ):
            raise PublicVerificationError("public verifier executable identity changed")

    def close(self) -> None:
        os.close(self.descriptor)

    def __enter__(self) -> PublicExecutableIdentity:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


def validate_public_executable(
    command: str, *, expected_owner_uid: int
) -> PublicExecutableIdentity:
    located = shutil.which(command) if not Path(command).is_absolute() else command
    if located is None:
        raise PublicVerificationError("public verifier executable is unavailable")
    path = Path(located).absolute()
    if expected_owner_uid == 0:
        validate_root_owned_ancestry(path)
    if path.is_symlink() or path.parent.is_symlink():
        raise PublicVerificationError("public verifier executable cannot be a symbolic link")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        observed = os.fstat(descriptor)
        parent = path.parent.stat()
        if not stat.S_ISREG(observed.st_mode) or not observed.st_mode & stat.S_IXUSR:
            raise PublicVerificationError("public verifier executable is not a regular executable")
        if observed.st_uid != expected_owner_uid or parent.st_uid != expected_owner_uid:
            raise PublicVerificationError("public verifier executable owner mismatch")
        if (observed.st_mode | parent.st_mode) & (stat.S_IWGRP | stat.S_IWOTH):
            raise PublicVerificationError("public verifier executable path is writable")
        path_observed = os.stat(path, follow_symlinks=False)
        if (path_observed.st_dev, path_observed.st_ino) != (observed.st_dev, observed.st_ino):
            raise PublicVerificationError("public verifier executable changed during preflight")
        return PublicExecutableIdentity(path, descriptor, observed.st_dev, observed.st_ino)
    except Exception:
        os.close(descriptor)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="traincapsule-verifier-verify-receipt")
    commands = parser.add_subparsers(dest="command", required=True)
    machine = commands.add_parser("verify-receipt")
    machine.add_argument("--receipt", type=Path, required=True)
    machine.add_argument("--candidate-sha", required=True)
    machine.add_argument("--candidate-tree-sha", required=True)
    machine.add_argument("--base-sha", required=True)
    machine.add_argument("--work-item-id", required=True)
    machine.add_argument("--candidate-manifest-digest", required=True)
    activation = commands.add_parser("verify-activation")
    activation.add_argument("--receipt", type=Path, required=True)
    activation.add_argument("--main-sha", required=True)
    activation.add_argument("--source-generation-id", required=True)
    activation.add_argument("--source-generation-digest", required=True)
    activation.add_argument("--controller-binary-digest", required=True)
    activation.add_argument("--controller-config-digest", required=True)
    ruleset = commands.add_parser("verify-ruleset-observation")
    ruleset.add_argument("--receipt", type=Path, required=True)
    ruleset.add_argument("--repository", required=True)
    ruleset.add_argument("--observation-digest", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        with validate_public_executable(
            sys.argv[0], expected_owner_uid=EXPECTED_OWNER_UID
        ) as executable:
            with PublicVerifier.from_public_roots(
                repository_root=Path.cwd(),
                config_root=CONFIG_ROOT,
                state_root=CONFIG_ROOT,
                receipt_root=RECEIPT_ROOT,
                expected_owner_uid=EXPECTED_OWNER_UID,
            ) as verifier:
                if args.command == "verify-receipt":
                    receipt = parse_receipt(args.receipt, MachinePolicyReceipt)
                    authorization = verifier.authorize_receipt(
                        receipt,
                        candidate_sha=args.candidate_sha,
                        candidate_tree_sha=args.candidate_tree_sha,
                        base_sha=args.base_sha,
                        work_item_id=args.work_item_id,
                        candidate_manifest_digest=args.candidate_manifest_digest,
                    )
                elif args.command == "verify-activation":
                    receipt = parse_receipt(args.receipt, ActivationReceipt)
                    authorization = verifier.authorize_activation(
                        receipt,
                        main_sha=args.main_sha,
                        source_generation_id=args.source_generation_id,
                        source_generation_digest=args.source_generation_digest,
                        controller_binary_digest=args.controller_binary_digest,
                        controller_config_digest=args.controller_config_digest,
                    )
                else:
                    authorization = parse_receipt(
                        args.receipt, RulesetObservationReceipt
                    )
                    verify_model_signature(
                        authorization,
                        load_public_key((CONFIG_ROOT / "ruleset-public-key.pem").read_bytes()),
                    )
                    if (
                        authorization.repository != args.repository
                        or authorization.observation_digest != args.observation_digest
                    ):
                        raise PublicVerificationError(
                            "ruleset observation receipt does not match live observation"
                        )
                    from datetime import UTC, datetime

                    now = datetime.now(UTC)
                    if authorization.observed_at > now or authorization.expires_at <= now:
                        raise PublicVerificationError("ruleset observation receipt is stale")
            executable.revalidate()
            sys.stdout.buffer.write(canonical_json_bytes(authorization))
        return 0
    except (OSError, ValueError, PublicVerificationError):
        print("independent public verifier rejected authorization", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
