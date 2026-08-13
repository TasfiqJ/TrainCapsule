"""Controller-owned, fail-closed boundary for consequential external actions."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from string import Formatter
from typing import ClassVar, Literal, Protocol, cast

from pydantic import (
    AwareDatetime,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from tcfactory.v3.base import DIGEST_PATTERN, SHA_PATTERN, to_camel
from tcfactory.v3.contracts_v31 import MachinePolicyReceiptV31, PolicyDecision, V31Model

_GENERATION_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class ExternalActionPolicyError(RuntimeError):
    """Raised when an installed action request violates its exact policy contract."""


class ExternalActionChannel(StrEnum):
    EMAIL = "EMAIL"
    CRM = "CRM"
    CALENDAR = "CALENDAR"


class ExternalActionStatus(StrEnum):
    SENT = "SENT"
    WAITING_EXTERNAL_CHANNEL = "WAITING_EXTERNAL_CHANNEL"


class ExternalActionReason(StrEnum):
    DELIVERED = "DELIVERED"
    ADAPTER_NOT_INSTALLED = "ADAPTER_NOT_INSTALLED"
    VERIFIER_NOT_INSTALLED = "VERIFIER_NOT_INSTALLED"
    BACKEND_NOT_INSTALLED = "BACKEND_NOT_INSTALLED"
    POLICY_VERIFIER_NOT_INSTALLED = "POLICY_VERIFIER_NOT_INSTALLED"
    JOURNAL_NOT_INSTALLED = "JOURNAL_NOT_INSTALLED"
    MACHINE_POLICY_UNVERIFIED = "MACHINE_POLICY_UNVERIFIED"
    MACHINE_POLICY_EXPIRED = "MACHINE_POLICY_EXPIRED"
    POLICY_ARTIFACT_UNVERIFIED = "POLICY_ARTIFACT_UNVERIFIED"
    IDEMPOTENCY_PENDING = "IDEMPOTENCY_PENDING"
    CHANNEL_UNAVAILABLE = "CHANNEL_UNAVAILABLE"


class ExternalActionModel(V31Model):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
        strict=True,
    )


class ExternalActionTemplate(ExternalActionModel):
    template_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    channel: ExternalActionChannel
    subject_template: str = Field(min_length=1, max_length=500)
    body_template: str = Field(min_length=1, max_length=16_000)
    variable_names: list[str] = Field(max_length=64)

    @field_validator("variable_names")
    @classmethod
    def validate_variable_names(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("template variable names must be unique")
        if any(not _is_identifier(value) for value in values):
            raise ValueError("template variable names must be simple identifiers")
        return values

    @model_validator(mode="after")
    def validate_exact_template(self) -> ExternalActionTemplate:
        observed = _template_fields(self.subject_template) | _template_fields(self.body_template)
        if observed != set(self.variable_names):
            raise ValueError("installed template fields must exactly match variable names")
        return self


class ExternalActionInstallation(ExternalActionModel):
    """All controller-owned prerequisites required to enable one exact action shape."""

    machine_policy_receipt: MachinePolicyReceiptV31
    independent_verifier_receipt_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    credential_reference: str = Field(pattern=r"^CREDREF:[A-Z0-9][A-Z0-9._/-]{2,127}$")
    backend_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    recipient_allowlist: list[str] = Field(min_length=1, max_length=256)
    legal_policy_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    legal_policy_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    safety_policy_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    safety_policy_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    machine_policy_scope: list[str] = Field(min_length=1, max_length=64)
    channel: ExternalActionChannel
    template: ExternalActionTemplate

    @field_validator("recipient_allowlist")
    @classmethod
    def validate_recipients(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("recipient allowlist entries must be unique")
        if any(not value or len(value) > 320 for value in values):
            raise ValueError("recipient allowlist contains an invalid entry")
        return values

    @model_validator(mode="after")
    def validate_installation(self) -> ExternalActionInstallation:
        # Re-parse so callers cannot smuggle a model_construct() receipt past validation.
        receipt = MachinePolicyReceiptV31.model_validate(
            self.machine_policy_receipt.model_dump(by_alias=True), strict=True
        )
        if receipt.decision is not PolicyDecision.PASS:
            raise ValueError("external action requires a PASS machine-policy receipt")
        if receipt.allowed_claims != ["EXTERNAL_ACTION"] or receipt.forbidden_claims:
            raise ValueError("machine-policy receipt claims must equal EXTERNAL_ACTION")
        if receipt.publication_scope != self.machine_policy_scope:
            raise ValueError("machine-policy receipt scope does not equal action scope")
        if self.template.channel is not self.channel:
            raise ValueError("installed template channel mismatch")
        return self


class ExternalActionRequest(ExternalActionModel):
    action_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    channel: ExternalActionChannel
    recipient: str = Field(min_length=1, max_length=320)
    template_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    variables: dict[str, str] = Field(max_length=64)
    machine_policy_receipt_id: str = Field(min_length=1, max_length=128)
    machine_policy_receipt_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    requested_at: AwareDatetime

    @field_validator("variables")
    @classmethod
    def validate_variables(cls, values: dict[str, str]) -> dict[str, str]:
        if any(not _is_identifier(key) for key in values):
            raise ValueError("action variable names must be simple identifiers")
        if any(len(value) > 16_000 for value in values.values()):
            raise ValueError("action variable exceeds the size limit")
        return values


class ExternalActionPayload(ExternalActionModel):
    action_id: str
    action_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    backend_id: str
    channel: ExternalActionChannel
    recipient: str
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=16_000)
    credential_reference: str
    idempotency_key: str = Field(pattern=DIGEST_PATTERN.pattern)
    delivery_generation_id: str = Field(pattern=r"^[0-9a-f]{32}$")


class ExternalDeliveryReceipt(ExternalActionModel):
    backend_id: str
    backend_delivery_id: str = Field(min_length=1, max_length=256)
    action_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    payload_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    idempotency_key: str = Field(pattern=DIGEST_PATTERN.pattern)
    delivery_generation_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    delivered_at: AwareDatetime
    delivery_digest: str = Field(pattern=DIGEST_PATTERN.pattern)

    @model_validator(mode="after")
    def validate_delivery_digest(self) -> ExternalDeliveryReceipt:
        expected = external_action_digest(self, exclude={"delivery_digest"})
        if self.delivery_digest != expected:
            raise ValueError("external delivery digest does not bind its receipt")
        return self


class ExternalActionOutcome(ExternalActionModel):
    action_id: str
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    request: ExternalActionRequest
    request_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    status: ExternalActionStatus
    reason: ExternalActionReason
    delivery_receipt: ExternalDeliveryReceipt | None = None
    unrelated_lanes_may_continue: Literal[True] = True

    @model_validator(mode="after")
    def validate_outcome(self) -> ExternalActionOutcome:
        if (
            self.request.action_id != self.action_id
            or self.request.work_item_id != self.work_item_id
            or self.request.candidate_sha != self.candidate_sha
        ):
            raise ValueError("external action outcome request identity mismatch")
        sent = self.status is ExternalActionStatus.SENT
        if sent != (self.delivery_receipt is not None):
            raise ValueError("only SENT outcomes may contain a delivery receipt")
        if sent != (self.reason is ExternalActionReason.DELIVERED):
            raise ValueError("delivery reason/status mismatch")
        if sent:
            assert self.delivery_receipt is not None
            if (
                self.delivery_receipt.action_digest != self.request_digest
                or self.delivery_receipt.idempotency_key != self.request_digest
                or self.delivery_receipt.delivered_at < self.request.requested_at
            ):
                raise ValueError("delivery is not bound to the exact action request")
        return self


class MachinePolicyReceiptVerifier(Protocol):
    def verify(self, receipt: MachinePolicyReceiptV31, *, now: datetime) -> str: ...


class ExternalPolicyArtifactVerifier(Protocol):
    def verify(self, *, policy_id: str, policy_digest: str) -> bool: ...


class ExternalActionBackend(Protocol):
    backend_id: str

    def is_available(
        self, *, channel: ExternalActionChannel, credential_reference: str
    ) -> bool: ...

    def send(self, payload: ExternalActionPayload) -> ExternalDeliveryReceipt: ...


class ServiceDirectoryOpener(Protocol):
    @property
    def path(self) -> Path: ...

    def open_fd(self) -> int: ...


class _JournalDisposition(StrEnum):
    RESERVED = "RESERVED"
    PENDING = "PENDING"
    RECOVERED = "RECOVERED"


@dataclass(frozen=True)
class _JournalResult:
    disposition: _JournalDisposition
    delivery_generation_id: str
    outcome: ExternalActionOutcome | None = None


class ExternalResponseConsumptionDisposition(StrEnum):
    """Durable response-application state for one delivery generation."""

    RESERVED = "RESERVED"
    RECOVERABLE = "RECOVERABLE"


@dataclass(frozen=True)
class ExternalResponseConsumption:
    disposition: ExternalResponseConsumptionDisposition
    response_receipt_id: str
    response_nonce: str
    response_digest: str
    delivery_generation_id: str


class ExternalActionJournal:
    """Durable controller journal preventing duplicate consequential sends."""

    def __init__(self, root: Path, *, root_opener: ServiceDirectoryOpener | None = None) -> None:
        if not root.is_absolute():
            raise ExternalActionPolicyError("external action journal root must be absolute")
        self.root = root
        self.root_opener = root_opener

    def reserve(self, action_digest: str) -> _JournalResult:
        root_fd = self._open_root()
        name = self._name(action_digest)
        delivery_generation_id = secrets.token_hex(16)
        pending = json.dumps(
            {
                "state": "PENDING",
                "actionDigest": action_digest,
                "deliveryGenerationId": delivery_generation_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        try:
            try:
                fd = os.open(
                    name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=root_fd,
                )
            except FileExistsError:
                existing = self._read(root_fd, name)
                try:
                    record = json.loads(existing)
                except json.JSONDecodeError as exc:
                    raise ExternalActionPolicyError(
                        "external action journal record is corrupt"
                    ) from exc
                if record.get("actionDigest") != action_digest:
                    raise ExternalActionPolicyError(
                        "external action journal digest mismatch"
                    ) from None
                existing_generation = record.get("deliveryGenerationId")
                if not isinstance(existing_generation, str) or not _GENERATION_PATTERN.fullmatch(
                    existing_generation
                ):
                    raise ExternalActionPolicyError(
                        "external action journal generation is invalid"
                    ) from None
                if record.get("state") == "PENDING":
                    return _JournalResult(
                        _JournalDisposition.PENDING, existing_generation
                    )
                if record.get("state") != "SENT" or not isinstance(record.get("outcome"), dict):
                    raise ExternalActionPolicyError(
                        "external action journal state is invalid"
                    ) from None
                try:
                    outcome = ExternalActionOutcome.model_validate(record["outcome"], strict=False)
                except ValidationError as exc:
                    raise ExternalActionPolicyError(
                        "external action journal outcome is invalid"
                    ) from exc
                if outcome.request_digest != action_digest:
                    raise ExternalActionPolicyError(
                        "journal outcome action binding mismatch"
                    ) from None
                if (
                    outcome.delivery_receipt is None
                    or outcome.delivery_receipt.delivery_generation_id
                    != existing_generation
                ):
                    raise ExternalActionPolicyError(
                        "journal outcome delivery generation mismatch"
                    ) from None
                return _JournalResult(
                    _JournalDisposition.RECOVERED, existing_generation, outcome
                )
            try:
                _write_all(fd, pending)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.fsync(root_fd)
            return _JournalResult(_JournalDisposition.RESERVED, delivery_generation_id)
        finally:
            os.close(root_fd)

    def commit(self, action_digest: str, outcome: ExternalActionOutcome) -> None:
        if (
            outcome.request_digest != action_digest
            or outcome.status is not ExternalActionStatus.SENT
        ):
            raise ExternalActionPolicyError("journal commit outcome is not a bound SENT result")
        root_fd = self._open_root()
        try:
            name = self._name(action_digest)
            try:
                fd = os.open(name, os.O_RDWR | os.O_NOFOLLOW, dir_fd=root_fd)
            except OSError as exc:
                raise ExternalActionPolicyError(
                    "external action journal reservation is missing"
                ) from exc
            try:
                metadata = os.fstat(fd)
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 1_048_576:
                    raise ExternalActionPolicyError("external action journal record is unsafe")
                existing = self._read_fd(fd)
                try:
                    pending = json.loads(existing)
                except json.JSONDecodeError as exc:
                    raise ExternalActionPolicyError(
                        "external action journal record is corrupt"
                    ) from exc
                generation = pending.get("deliveryGenerationId")
                if (
                    pending.get("state") != "PENDING"
                    or pending.get("actionDigest") != action_digest
                    or not isinstance(generation, str)
                    or outcome.delivery_receipt is None
                    or outcome.delivery_receipt.delivery_generation_id != generation
                ):
                    raise ExternalActionPolicyError(
                        "journal commit delivery generation mismatch"
                    )
                record = json.dumps(
                    {
                        "state": "SENT",
                        "actionDigest": action_digest,
                        "deliveryGenerationId": generation,
                        "outcome": outcome.model_dump(mode="json", by_alias=True),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
                os.ftruncate(fd, 0)
                os.lseek(fd, 0, os.SEEK_SET)
                _write_all(fd, record)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.fsync(root_fd)
        finally:
            os.close(root_fd)

    def reserve_response_consumption(
        self,
        outcome: ExternalActionOutcome,
        *,
        response_receipt_id: str,
        response_nonce: str,
        response_digest: str,
    ) -> ExternalResponseConsumption:
        """Atomically reserve one response for one exact delivery generation."""

        if outcome.status is not ExternalActionStatus.SENT or outcome.delivery_receipt is None:
            raise ExternalActionPolicyError("response consumption requires a SENT action")
        delivery = outcome.delivery_receipt
        root_fd = self._open_root()
        try:
            action_record = self._decode_record(
                self._read(root_fd, self._name(outcome.request_digest)),
                "external action journal record",
            )
            if (
                action_record.get("state") != "SENT"
                or action_record.get("actionDigest") != outcome.request_digest
                or action_record.get("deliveryGenerationId")
                != delivery.delivery_generation_id
                or action_record.get("outcome")
                != outcome.model_dump(mode="json", by_alias=True)
            ):
                raise ExternalActionPolicyError(
                    "response consumption action generation mismatch"
                )
            record = {
                "state": "PENDING_TERMINAL_TRANSITION",
                "actionDigest": outcome.request_digest,
                "deliveryGenerationId": delivery.delivery_generation_id,
                "responseReceiptId": response_receipt_id,
                "responseNonce": response_nonce,
                "responseDigest": response_digest,
            }
            raw = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
            name = self._response_name(outcome.request_digest)
            try:
                fd = os.open(
                    name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=root_fd,
                )
            except FileExistsError:
                existing = self._decode_record(
                    self._read(root_fd, name), "external response consumption record"
                )
                if existing != record:
                    raise ExternalActionPolicyError(
                        "delivery generation was already consumed by another response"
                    ) from None
                return ExternalResponseConsumption(
                    disposition=ExternalResponseConsumptionDisposition.RECOVERABLE,
                    response_receipt_id=response_receipt_id,
                    response_nonce=response_nonce,
                    response_digest=response_digest,
                    delivery_generation_id=delivery.delivery_generation_id,
                )
            try:
                _write_all(fd, raw)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.fsync(root_fd)
            return ExternalResponseConsumption(
                disposition=ExternalResponseConsumptionDisposition.RESERVED,
                response_receipt_id=response_receipt_id,
                response_nonce=response_nonce,
                response_digest=response_digest,
                delivery_generation_id=delivery.delivery_generation_id,
            )
        finally:
            os.close(root_fd)

    def commit_response_consumption(
        self,
        outcome: ExternalActionOutcome,
        consumption: ExternalResponseConsumption,
    ) -> None:
        """Mark a reserved response applied after the terminal queue transition."""

        if outcome.delivery_receipt is None:
            raise ExternalActionPolicyError("response consumption omitted delivery")
        expected = {
            "state": "PENDING_TERMINAL_TRANSITION",
            "actionDigest": outcome.request_digest,
            "deliveryGenerationId": outcome.delivery_receipt.delivery_generation_id,
            "responseReceiptId": consumption.response_receipt_id,
            "responseNonce": consumption.response_nonce,
            "responseDigest": consumption.response_digest,
        }
        root_fd = self._open_root()
        try:
            name = self._response_name(outcome.request_digest)
            current = self._decode_record(
                self._read(root_fd, name), "external response consumption record"
            )
            if current != expected:
                raise ExternalActionPolicyError(
                    "external response consumption cannot be committed"
                )
            committed = {**expected, "state": "APPLIED"}
            self._atomic_replace(
                root_fd,
                name,
                json.dumps(committed, sort_keys=True, separators=(",", ":")).encode(),
            )
        finally:
            os.close(root_fd)

    def _open_root(self) -> int:
        if self.root_opener is not None:
            if self.root_opener.path != self.root:
                raise ExternalActionPolicyError("external action journal guard path mismatch")
            try:
                return self.root_opener.open_fd()
            except Exception as exc:
                raise ExternalActionPolicyError(
                    "external action journal root identity changed"
                ) from exc
        try:
            return os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError as exc:
            raise ExternalActionPolicyError(
                "external action journal root must be a real pre-created directory"
            ) from exc

    @staticmethod
    def _name(action_digest: str) -> str:
        if not DIGEST_PATTERN.fullmatch(action_digest):
            raise ExternalActionPolicyError("external action journal digest is invalid")
        return f"{action_digest.removeprefix('sha256:')}.json"

    @staticmethod
    def _response_name(action_digest: str) -> str:
        return f"response-{ExternalActionJournal._name(action_digest)}"

    @staticmethod
    def _decode_record(raw: bytes, label: str) -> dict[str, object]:
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ExternalActionPolicyError(f"{label} is corrupt") from exc
        if not isinstance(record, dict):
            raise ExternalActionPolicyError(f"{label} is invalid")
        return cast(dict[str, object], record)

    @staticmethod
    def _atomic_replace(root_fd: int, name: str, raw: bytes) -> None:
        temporary = f".{name}.{secrets.token_hex(8)}.tmp"
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=root_fd,
        )
        try:
            _write_all(fd, raw)
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.replace(temporary, name, src_dir_fd=root_fd, dst_dir_fd=root_fd)
            os.fsync(root_fd)
        except Exception:
            with suppress(OSError):
                os.unlink(temporary, dir_fd=root_fd)
            raise

    @staticmethod
    def _read(root_fd: int, name: str) -> bytes:
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd)
        except OSError as exc:
            raise ExternalActionPolicyError("external action journal record is unsafe") from exc
        try:
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 1_048_576:
                raise ExternalActionPolicyError("external action journal record is unsafe")
            return ExternalActionJournal._read_fd(fd)
        finally:
            os.close(fd)

    @staticmethod
    def _read_fd(fd: int) -> bytes:
        os.lseek(fd, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        remaining = 1_048_577
        while remaining > 0:
            chunk = os.read(fd, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        value = b"".join(chunks)
        if len(value) > 1_048_576:
            raise ExternalActionPolicyError("external action journal record is unbounded")
        return value


class ExternalActionAdapter:
    """Backend-neutral adapter that remains disabled until every prerequisite exists."""

    def __init__(
        self,
        *,
        installation: ExternalActionInstallation | None = None,
        verifier: MachinePolicyReceiptVerifier | None = None,
        policy_verifier: ExternalPolicyArtifactVerifier | None = None,
        backend: ExternalActionBackend | None = None,
        journal: ExternalActionJournal | None = None,
    ) -> None:
        self.installation = installation
        self.verifier = verifier
        self.policy_verifier = policy_verifier
        self.backend = backend
        self.journal = journal

    def execute(self, request: ExternalActionRequest, *, now: datetime) -> ExternalActionOutcome:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ExternalActionPolicyError("external action time must be timezone-aware")
        provisional_digest = external_action_digest(request)
        if self.installation is None:
            return _waiting(request, provisional_digest, ExternalActionReason.ADAPTER_NOT_INSTALLED)
        if self.verifier is None:
            return _waiting(
                request, provisional_digest, ExternalActionReason.VERIFIER_NOT_INSTALLED
            )
        if self.policy_verifier is None:
            return _waiting(
                request,
                provisional_digest,
                ExternalActionReason.POLICY_VERIFIER_NOT_INSTALLED,
            )
        if self.backend is None:
            return _waiting(request, provisional_digest, ExternalActionReason.BACKEND_NOT_INSTALLED)
        if self.journal is None:
            return _waiting(request, provisional_digest, ExternalActionReason.JOURNAL_NOT_INSTALLED)

        installed = self.installation
        receipt = installed.machine_policy_receipt
        if receipt.expires_at <= now:
            return _waiting(
                request, provisional_digest, ExternalActionReason.MACHINE_POLICY_EXPIRED
            )
        try:
            verifier_receipt_digest = self.verifier.verify(receipt, now=now)
        except Exception:
            return _waiting(
                request, provisional_digest, ExternalActionReason.MACHINE_POLICY_UNVERIFIED
            )
        if verifier_receipt_digest != installed.independent_verifier_receipt_digest:
            return _waiting(
                request, provisional_digest, ExternalActionReason.MACHINE_POLICY_UNVERIFIED
            )
        try:
            policies_verified = self.policy_verifier.verify(
                policy_id=installed.legal_policy_id,
                policy_digest=installed.legal_policy_digest,
            ) and self.policy_verifier.verify(
                policy_id=installed.safety_policy_id,
                policy_digest=installed.safety_policy_digest,
            )
        except Exception:
            policies_verified = False
        if not policies_verified:
            return _waiting(
                request, provisional_digest, ExternalActionReason.POLICY_ARTIFACT_UNVERIFIED
            )

        receipt_digest = external_action_digest(receipt)
        if (
            request.machine_policy_receipt_id != receipt.receipt_id
            or request.machine_policy_receipt_digest != receipt_digest
            or request.work_item_id != receipt.work_item_id
            or request.candidate_sha != receipt.candidate_sha
        ):
            raise ExternalActionPolicyError("external action machine-policy binding mismatch")
        if request.channel is not installed.channel:
            raise ExternalActionPolicyError("external action channel is not installed")
        if request.recipient not in set(installed.recipient_allowlist):
            raise ExternalActionPolicyError("external action recipient is not allowlisted")
        if request.template_id != installed.template.template_id:
            raise ExternalActionPolicyError("external action template is not installed")
        if set(request.variables) != set(installed.template.variable_names):
            raise ExternalActionPolicyError("external action variables do not match the template")
        if self.backend.backend_id != installed.backend_id:
            raise ExternalActionPolicyError("external action backend identity mismatch")
        action_digest = external_action_authorization_digest(request, installed)
        if receipt.request_digest != action_digest:
            raise ExternalActionPolicyError(
                "machine-policy receipt is not bound to the exact external action"
            )
        if not self.backend.is_available(
            channel=installed.channel,
            credential_reference=installed.credential_reference,
        ):
            return _waiting(request, action_digest, ExternalActionReason.CHANNEL_UNAVAILABLE)

        journal_result = self.journal.reserve(action_digest)
        if journal_result.disposition is _JournalDisposition.RECOVERED:
            if journal_result.outcome is None:
                raise ExternalActionPolicyError("journal recovery omitted its outcome")
            return journal_result.outcome
        if journal_result.disposition is _JournalDisposition.PENDING:
            return _waiting(request, action_digest, ExternalActionReason.IDEMPOTENCY_PENDING)
        payload = ExternalActionPayload(
            schema_version="3.1",
            action_id=request.action_id,
            action_digest=action_digest,
            backend_id=installed.backend_id,
            channel=request.channel,
            recipient=request.recipient,
            subject=installed.template.subject_template.format_map(request.variables),
            body=installed.template.body_template.format_map(request.variables),
            credential_reference=installed.credential_reference,
            idempotency_key=action_digest,
            delivery_generation_id=journal_result.delivery_generation_id,
        )
        payload_digest = external_action_digest(payload)
        try:
            delivery = self.backend.send(payload)
        except Exception:
            return _waiting(request, action_digest, ExternalActionReason.IDEMPOTENCY_PENDING)
        try:
            delivery = ExternalDeliveryReceipt.model_validate(
                delivery.model_dump(by_alias=True), strict=True
            )
        except ValidationError as exc:
            raise ExternalActionPolicyError("backend delivery receipt is invalid") from exc
        if (
            delivery.idempotency_key != action_digest
            or delivery.action_digest != action_digest
            or delivery.payload_digest != payload_digest
            or delivery.backend_id != installed.backend_id
            or delivery.delivery_generation_id
            != journal_result.delivery_generation_id
        ):
            raise ExternalActionPolicyError("backend delivery receipt idempotency mismatch")
        outcome = ExternalActionOutcome(
            schema_version="3.1",
            action_id=request.action_id,
            work_item_id=request.work_item_id,
            candidate_sha=request.candidate_sha,
            request=request,
            request_digest=action_digest,
            status=ExternalActionStatus.SENT,
            reason=ExternalActionReason.DELIVERED,
            delivery_receipt=delivery,
        )
        self.journal.commit(action_digest, outcome)
        return outcome


EXTERNAL_ACTION_CONTRACTS: dict[str, type[ExternalActionModel]] = {
    "external-action-template": ExternalActionTemplate,
    "external-action-installation": ExternalActionInstallation,
    "external-action-request": ExternalActionRequest,
    "external-action-payload": ExternalActionPayload,
    "external-delivery-receipt": ExternalDeliveryReceipt,
    "external-action-outcome": ExternalActionOutcome,
}


def _waiting(
    request: ExternalActionRequest,
    request_digest: str,
    reason: ExternalActionReason,
) -> ExternalActionOutcome:
    return ExternalActionOutcome(
        schema_version="3.1",
        action_id=request.action_id,
        work_item_id=request.work_item_id,
        candidate_sha=request.candidate_sha,
        request=request,
        request_digest=request_digest,
        status=ExternalActionStatus.WAITING_EXTERNAL_CHANNEL,
        reason=reason,
        delivery_receipt=None,
    )


def _template_fields(value: str) -> set[str]:
    fields: set[str] = set()
    try:
        parsed = Formatter().parse(value)
        for _, field, format_spec, conversion in parsed:
            if field is None:
                continue
            if not _is_identifier(field) or format_spec or conversion:
                raise ValueError("template fields must be unformatted simple identifiers")
            fields.add(field)
    except (KeyError, ValueError) as exc:
        raise ValueError("external action template is invalid") from exc
    return fields


def _is_identifier(value: str) -> bool:
    return value.isidentifier() and value.isascii() and not value.startswith("_")


def external_action_authorization_digest(
    request: ExternalActionRequest, installation: ExternalActionInstallation
) -> str:
    """Bind the receipt to the exact action plus every installed policy capability."""

    payload = {
        "action": request.model_dump(
            mode="json",
            by_alias=True,
            exclude={"machine_policy_receipt_id", "machine_policy_receipt_digest"},
        ),
        "installation": {
            "independentVerifierReceiptDigest": (installation.independent_verifier_receipt_digest),
            "credentialReference": installation.credential_reference,
            "backendId": installation.backend_id,
            "recipientAllowlist": installation.recipient_allowlist,
            "legalPolicyId": installation.legal_policy_id,
            "legalPolicyDigest": installation.legal_policy_digest,
            "safetyPolicyId": installation.safety_policy_id,
            "safetyPolicyDigest": installation.safety_policy_digest,
            "machinePolicyScope": installation.machine_policy_scope,
            "channel": installation.channel.value,
            "template": installation.template.model_dump(mode="json", by_alias=True),
        },
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(serialized).hexdigest()}"


def external_action_digest(model: V31Model, *, exclude: set[str] | None = None) -> str:
    """Return the canonical digest used for policy and idempotency bindings."""

    serialized = json.dumps(
        model.model_dump(mode="json", by_alias=True, exclude=exclude or set()),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"sha256:{hashlib.sha256(serialized).hexdigest()}"


def _write_all(fd: int, value: bytes) -> None:
    view = memoryview(value)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise ExternalActionPolicyError("external action journal write failed")
        view = view[written:]
