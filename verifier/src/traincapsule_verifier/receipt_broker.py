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
        activation_root: TrustedRoot | None = None,
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
        if activation_root is not None:
            if activation_root.expected_uid != public_root.expected_uid:
                raise ReceiptPromotionError(
                    "activation selector and public receipt roots must share root ownership"
                )
            if (activation_root.device, activation_root.inode) in {
                (outbox_root.device, outbox_root.inode),
                (public_root.device, public_root.inode),
            }:
                raise ReceiptPromotionError(
                    "activation selector root must be distinct from broker roots"
                )
        self.verifier = verifier
        self.outbox_root = outbox_root
        self.public_root = public_root
        self.activation_root = activation_root

    def _select_current_activation(
        self, activation: ActivationReceipt, canonical: bytes
    ) -> None:
        if self.activation_root is None:
            return
        try:
            current_raw = read_bounded_file(
                self.activation_root,
                "current.json",
                maximum_bytes=MAX_RECEIPT_BYTES,
                expected_file_uid=self.activation_root.expected_uid,
            )
        except FileNotFoundError:
            current_raw = None
        if current_raw is not None:
            current = ActivationReceipt.model_validate_json(current_raw, strict=True)
            if canonical_json_bytes(current) != current_raw:
                raise ReceiptPromotionError(
                    "current activation selector bytes are not canonical"
                )
            if current.issued_at > activation.issued_at:
                return
            if current.issued_at == activation.issued_at:
                if current_raw != canonical:
                    raise ReceiptPromotionError(
                        "activation selector timestamp conflicts with different bytes"
                    )
                return
        pending = f".{activation.receipt_id}.current.pending"
        try:
            atomic_write_new(self.activation_root, pending, canonical, mode=0o644)
        except TrustedPathError:
            if (
                read_bounded_file(
                    self.activation_root,
                    pending,
                    maximum_bytes=MAX_RECEIPT_BYTES,
                    expected_file_uid=self.activation_root.expected_uid,
                )
                != canonical
            ):
                raise ReceiptPromotionError(
                    "activation selector recovery bytes conflict"
                ) from None
        os.rename(
            pending,
            "current.json",
            src_dir_fd=self.activation_root.descriptor,
            dst_dir_fd=self.activation_root.descriptor,
        )
        os.fsync(self.activation_root.descriptor)

    def _select_current_machine(
        self, machine: MachinePolicyReceipt, canonical: bytes
    ) -> str:
        selector = f"machine-policy/{machine.work_item_id}/{machine.candidate_sha}.json"
        try:
            current_raw = read_bounded_file(
                self.public_root,
                selector,
                maximum_bytes=MAX_RECEIPT_BYTES,
                expected_file_uid=self.public_root.expected_uid,
            )
        except FileNotFoundError:
            current_raw = None
        if current_raw is not None:
            current = MachinePolicyReceipt.model_validate_json(current_raw, strict=True)
            if canonical_json_bytes(current) != current_raw:
                raise ReceiptPromotionError(
                    "current machine-policy selector bytes are not canonical"
                )
            if current.issued_at > machine.issued_at:
                return selector
            if current.issued_at == machine.issued_at:
                if current_raw != canonical:
                    raise ReceiptPromotionError(
                        "machine-policy selector timestamp conflicts with different bytes"
                    )
                return selector
        # Historical immutable bytes remain replayable, but selector advancement
        # must still be currently authorized so an expired or newly revoked
        # receipt cannot displace a usable selection during crash recovery.
        self.verifier.verify_machine_receipt_authority(machine)
        parent, name = selector.rsplit("/", 1)
        pending = f"{parent}/.{machine.receipt_id}.{name}.pending"
        try:
            atomic_write_new(self.public_root, pending, canonical, mode=0o644)
        except TrustedPathError:
            if (
                read_bounded_file(
                    self.public_root,
                    pending,
                    maximum_bytes=MAX_RECEIPT_BYTES,
                    expected_file_uid=self.public_root.expected_uid,
                )
                != canonical
            ):
                raise ReceiptPromotionError(
                    "machine-policy selector recovery bytes conflict"
                ) from None
        os.rename(
            pending,
            selector,
            src_dir_fd=self.public_root.descriptor,
            dst_dir_fd=self.public_root.descriptor,
        )
        os.fsync(self.public_root.descriptor)
        return selector

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
                receipt_type: Literal["machine-policy", "activation"] = "machine-policy"
                receipt_id = machine.receipt_id
                activation = None
            elif outbox_name.startswith("ACT:"):
                activation = ActivationReceipt.model_validate_json(raw, strict=True)
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
            public_relative_path = expected_name
            already_promoted = False
            try:
                observed = read_bounded_file(
                    self.public_root,
                    expected_name,
                    maximum_bytes=MAX_RECEIPT_BYTES,
                    expected_file_uid=os.fstat(self.public_root.descriptor).st_uid,
                )
                if observed != canonical:
                    raise ReceiptPromotionError(
                        "public receipt identity already exists with different bytes"
                    )
                already_promoted = True
            except FileNotFoundError:
                pass
            if machine is not None:
                public_relative_path = (
                    f"machine-policy/{machine.work_item_id}/{machine.candidate_sha}.json"
                )
            if already_promoted:
                make_publicly_readable(self.public_root, expected_name)
                if machine is not None:
                    self._select_current_machine(machine, canonical)
                    make_publicly_readable(self.public_root, public_relative_path)
                elif activation is not None:
                    self._select_current_activation(activation, canonical)
                return ReceiptPromotionResult(
                    state="ALREADY_PROMOTED",
                    receipt_type=receipt_type,
                    receipt_id=receipt_id,
                    receipt_digest=digest,
                    public_relative_path=public_relative_path,
                )
            if machine is not None:
                self.verifier.verify_machine_receipt_authority(machine)
            elif activation is not None:
                self.verifier.verify_activation_authority(activation)
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
            if machine is not None:
                self._select_current_machine(machine, canonical)
                make_publicly_readable(self.public_root, public_relative_path)
            elif activation is not None:
                self._select_current_activation(activation, canonical)
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
