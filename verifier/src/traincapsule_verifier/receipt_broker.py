"""Minimal root broker for public promotion of service-issued receipts."""

from __future__ import annotations

import os
from typing import Literal

from pydantic import Field, ValidationError

from .canonical import canonical_json_bytes, sha256_digest
from .filesystem import (
    TrustedPathError,
    TrustedRoot,
    atomic_write_new,
    make_publicly_readable,
    read_bounded_file,
    strict_json_loads,
)
from .models import ActivationReceipt, MachinePolicyReceipt, StrictModel
from .public_verifier import MAX_RECEIPT_BYTES, PublicVerificationError, PublicVerifier


class ReceiptPromotionError(RuntimeError):
    pass


class ReceiptPromotionResult(StrictModel):
    state: Literal["PROMOTED", "ALREADY_PROMOTED"]
    receipt_type: Literal["machine-policy", "activation"]
    receipt_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    receipt_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    public_relative_path: str


class RootReceiptBroker:
    """Reverify service outbox bytes and copy them into the public receipt root."""

    def __init__(
        self,
        *,
        verifier: PublicVerifier,
        outbox_root: TrustedRoot,
        public_root: TrustedRoot,
    ) -> None:
        if outbox_root.expected_uid == public_root.expected_uid:
            raise ReceiptPromotionError("service outbox and public root must have different owners")
        if (outbox_root.device, outbox_root.inode) == (public_root.device, public_root.inode):
            raise ReceiptPromotionError("service outbox and public root must be distinct")
        if (verifier.receipt_root.device, verifier.receipt_root.inode) != (
            public_root.device,
            public_root.inode,
        ):
            raise ReceiptPromotionError("broker and public verifier receipt roots differ")
        self.verifier = verifier
        self.outbox_root = outbox_root
        self.public_root = public_root

    def promote(self, outbox_name: str) -> ReceiptPromotionResult:
        if not outbox_name.endswith(".json"):
            raise ReceiptPromotionError("outbox receipt name must end in .json")
        try:
            raw = read_bounded_file(self.outbox_root, outbox_name, maximum_bytes=MAX_RECEIPT_BYTES)
            strict_json_loads(raw)
            machine: MachinePolicyReceipt | None
            activation: ActivationReceipt | None
            if outbox_name.startswith("MPOL:"):
                machine = MachinePolicyReceipt.model_validate_json(raw, strict=True)
                self.verifier.verify_machine_receipt_authority(machine)
                receipt_type: Literal["machine-policy", "activation"] = "machine-policy"
                receipt_id = machine.receipt_id
                activation = None
            elif outbox_name.startswith("ACT:"):
                activation = ActivationReceipt.model_validate_json(raw, strict=True)
                self.verifier.verify_activation_authority(activation)
                receipt_type = "activation"
                receipt_id = activation.receipt_id
                machine = None
            else:
                raise ReceiptPromotionError("outbox filename has no recognized receipt type")
            model = machine if machine is not None else activation
            if model is None:
                raise ReceiptPromotionError("outbox receipt contract is invalid")
            canonical = canonical_json_bytes(model)
            if canonical != raw:
                raise ReceiptPromotionError("outbox receipt bytes are not canonical")
            expected_name = f"{receipt_id}.json"
            if outbox_name != expected_name:
                raise ReceiptPromotionError(
                    "outbox filename does not match signed receipt identity"
                )
            digest = sha256_digest(canonical)
            try:
                atomic_write_new(self.public_root, expected_name, canonical)
                state: Literal["PROMOTED", "ALREADY_PROMOTED"] = "PROMOTED"
            except TrustedPathError:
                observed = read_bounded_file(
                    self.public_root,
                    expected_name,
                    maximum_bytes=MAX_RECEIPT_BYTES,
                    expected_file_uid=os.fstat(self.public_root.descriptor).st_uid,
                )
                if observed != canonical:
                    raise ReceiptPromotionError(
                        "public receipt identity already exists with different bytes"
                    ) from None
                state = "ALREADY_PROMOTED"
            make_publicly_readable(self.public_root, expected_name)
            public_relative_path = expected_name
            if machine is not None:
                public_relative_path = (
                    f"machine-policy/{machine.work_item_id}/{machine.candidate_sha}.json"
                )
                try:
                    atomic_write_new(self.public_root, public_relative_path, canonical)
                except TrustedPathError:
                    selected = read_bounded_file(
                        self.public_root,
                        public_relative_path,
                        maximum_bytes=MAX_RECEIPT_BYTES,
                        expected_file_uid=os.fstat(self.public_root.descriptor).st_uid,
                    )
                    if selected != canonical:
                        raise ReceiptPromotionError(
                            "machine-policy selector conflicts for exact work item/SHA"
                        ) from None
                make_publicly_readable(self.public_root, public_relative_path)
            return ReceiptPromotionResult(
                state=state,
                receipt_type=receipt_type,
                receipt_id=receipt_id,
                receipt_digest=digest,
                public_relative_path=public_relative_path,
            )
        except ReceiptPromotionError:
            raise
        except (OSError, TrustedPathError, ValidationError, ValueError, PublicVerificationError):
            raise ReceiptPromotionError("root broker rejected outbox receipt") from None


def assert_distinct_root_identities(*roots: TrustedRoot) -> None:
    identities = [(root.device, root.inode) for root in roots]
    if len(identities) != len(set(identities)):
        raise ReceiptPromotionError("broker trust roots must be distinct directories")
    if any(os.fstat(root.descriptor).st_uid != root.expected_uid for root in roots):
        raise ReceiptPromotionError("broker trust-root owner changed")
