"""Offline interface for a separately credentialed GitHub App check worker.

No network or credential implementation lives in this distribution.  A production
adapter must poll GitHub as an installed App and provide idempotent lookup by the
action digest before publication.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol

from pydantic import Field

from .canonical import canonical_json_bytes, sha256_digest
from .filesystem import (
    TrustedPathError,
    TrustedRoot,
    atomic_write_new,
    read_bounded_file,
    strict_json_loads,
)
from .models import Digest, GitSha, Identifier, MachinePolicyReceipt, StrictModel, V31Model
from .public_verifier import PublicVerifier


class CheckPublisherUnavailable(RuntimeError):
    """Typed non-blocking external-channel state."""

    state: Literal["WAITING_EXTERNAL_CHANNEL"] = "WAITING_EXTERNAL_CHANNEL"


class CheckPublisherPolicy(V31Model):
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    github_app_id: int = Field(gt=0)
    installation_id: int = Field(gt=0)
    backend_id: Identifier
    credential_reference: str = Field(
        pattern=r"^CREDENTIAL:[A-Z0-9][A-Z0-9._:-]{2,116}$"
    )
    check_name: Literal["TrainCapsule / Machine policy"]


class CheckEvent(V31Model):
    event_id: Identifier
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    github_app_id: int = Field(gt=0)
    installation_id: int = Field(gt=0)
    candidate_sha: GitSha
    candidate_tree_sha: GitSha
    base_sha: GitSha
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    candidate_manifest_digest: Digest
    receipt_id: Identifier
    receipt_digest: Digest


class CheckPublishRequest(V31Model):
    action_digest: Digest
    repository: str
    github_app_id: int
    installation_id: int
    backend_id: Identifier
    credential_reference: Identifier
    check_name: Literal["TrainCapsule / Machine policy"]
    candidate_sha: GitSha
    conclusion: Literal["success"]
    receipt_id: Identifier
    receipt_digest: Digest


class CheckDeliveryReceipt(V31Model):
    action_digest: Digest
    backend_id: Identifier
    repository: str
    github_app_id: int
    installation_id: int
    external_check_id: str = Field(min_length=1, max_length=256)
    check_name: Literal["TrainCapsule / Machine policy"]
    candidate_sha: GitSha
    conclusion: Literal["success"]
    receipt_id: Identifier
    receipt_digest: Digest


class CheckPublisherBackend(Protocol):
    """Credential-owning adapter implemented and installed outside this package."""

    @property
    def backend_id(self) -> str: ...

    @property
    def github_app_id(self) -> int: ...

    def poll(self, *, after_event_id: str | None, limit: int) -> Sequence[CheckEvent]: ...

    def lookup(self, *, request: CheckPublishRequest) -> CheckDeliveryReceipt | None:
        """Reconcile an already-reserved action without creating a check."""
        ...

    def publish(self, request: CheckPublishRequest) -> CheckDeliveryReceipt:
        """Publish idempotently by request.action_digest or fail before side effects."""
        ...


class CheckProcessResult(V31Model):
    state: Literal["PUBLISHED", "ALREADY_PUBLISHED", "WAITING_EXTERNAL_CHANNEL"]
    event_id: Identifier
    action_digest: Digest | None = None
    external_check_id: str | None = None


def check_action_digest(request: CheckPublishRequest) -> str:
    payload = request.model_dump(mode="json", by_alias=True)
    payload.pop("actionDigest")
    return sha256_digest(canonical_json_bytes(payload))


class CheckPublisherWorker:
    """Durable single-event worker with exact candidate/check/receipt binding."""

    def __init__(
        self,
        *,
        verifier: PublicVerifier,
        policy: CheckPublisherPolicy,
        journal_root: TrustedRoot,
        backend: CheckPublisherBackend,
    ) -> None:
        if backend.backend_id != policy.backend_id:
            raise ValueError("check backend identity does not match installed policy")
        if backend.github_app_id != policy.github_app_id:
            raise ValueError("GitHub App identity does not match installed policy")
        self.verifier = verifier
        self.policy = policy
        self.journal_root = journal_root
        self.backend = backend

    def _request(self, event: CheckEvent) -> CheckPublishRequest:
        if (
            event.repository != self.policy.repository
            or event.github_app_id != self.policy.github_app_id
            or event.installation_id != self.policy.installation_id
        ):
            raise ValueError("check event repository or installation mismatch")
        receipt: MachinePolicyReceipt = self.verifier.load_machine_receipt(event.receipt_id)
        authorization = self.verifier.authorize_receipt(
            receipt,
            candidate_sha=event.candidate_sha,
            candidate_tree_sha=event.candidate_tree_sha,
            base_sha=event.base_sha,
            work_item_id=event.work_item_id,
            candidate_manifest_digest=event.candidate_manifest_digest,
        )
        if authorization.receipt_digest != event.receipt_digest:
            raise ValueError("check event receipt digest mismatch")
        provisional = CheckPublishRequest(
            schema_version="3.1",
            action_digest="sha256:" + "0" * 64,
            repository=event.repository,
            github_app_id=event.github_app_id,
            installation_id=event.installation_id,
            backend_id=self.policy.backend_id,
            credential_reference=self.policy.credential_reference,
            check_name=authorization.check_name,
            candidate_sha=authorization.candidate_sha,
            conclusion=authorization.conclusion,
            receipt_id=authorization.receipt_id,
            receipt_digest=authorization.receipt_digest,
        )
        return provisional.model_copy(update={"action_digest": check_action_digest(provisional)})

    def _read_journal[T: StrictModel](self, relative: str, model: type[T]) -> T:
        raw = read_bounded_file(self.journal_root, relative, maximum_bytes=65_536)
        strict_json_loads(raw)
        return model.model_validate_json(raw, strict=True)

    @staticmethod
    def _validate_delivery(
        request: CheckPublishRequest, delivery: CheckDeliveryReceipt
    ) -> None:
        expected = (
            (delivery.action_digest, request.action_digest),
            (delivery.backend_id, request.backend_id),
            (delivery.repository, request.repository),
            (delivery.github_app_id, request.github_app_id),
            (delivery.installation_id, request.installation_id),
            (delivery.check_name, request.check_name),
            (delivery.candidate_sha, request.candidate_sha),
            (delivery.conclusion, request.conclusion),
            (delivery.receipt_id, request.receipt_id),
            (delivery.receipt_digest, request.receipt_digest),
        )
        if any(observed != wanted for observed, wanted in expected):
            raise ValueError("check delivery is not bound to the exact reserved action")

    def process(self, event: CheckEvent) -> CheckProcessResult:
        request = self._request(event)
        key = request.action_digest.removeprefix("sha256:")
        claim_name = f"{key}.claim.json"
        delivery_name = f"{key}.delivery.json"
        try:
            delivery = self._read_journal(delivery_name, CheckDeliveryReceipt)
            self._validate_delivery(request, delivery)
            return CheckProcessResult(
                schema_version="3.1",
                state="ALREADY_PUBLISHED",
                event_id=event.event_id,
                action_digest=request.action_digest,
                external_check_id=delivery.external_check_id,
            )
        except FileNotFoundError:
            pass
        try:
            atomic_write_new(self.journal_root, claim_name, canonical_json_bytes(request))
            reserved_here = True
        except TrustedPathError as exc:
            reserved_here = False
            existing = self._read_journal(claim_name, CheckPublishRequest)
            if existing != request or check_action_digest(existing) != request.action_digest:
                raise ValueError(
                    "check journal claim does not match requested action"
                ) from exc
        try:
            delivery = self.backend.lookup(request=request)
            if delivery is None:
                if not reserved_here:
                    raise CheckPublisherUnavailable("reserved check awaits backend reconciliation")
                delivery = self.backend.publish(request)
            self._validate_delivery(request, delivery)
            try:
                atomic_write_new(
                    self.journal_root, delivery_name, canonical_json_bytes(delivery)
                )
            except TrustedPathError:
                persisted = self._read_journal(delivery_name, CheckDeliveryReceipt)
                self._validate_delivery(request, persisted)
                delivery = persisted
        except CheckPublisherUnavailable:
            raise
        except Exception:
            raise CheckPublisherUnavailable("external check channel is unavailable") from None
        return CheckProcessResult(
            schema_version="3.1",
            state="PUBLISHED",
            event_id=event.event_id,
            action_digest=request.action_digest,
            external_check_id=delivery.external_check_id,
        )

    def run_once(
        self, *, after_event_id: str | None = None, limit: int = 50
    ) -> list[CheckProcessResult]:
        if limit < 1 or limit > 100:
            raise ValueError("poll limit must be between 1 and 100")
        try:
            events = self.backend.poll(after_event_id=after_event_id, limit=limit)
        except Exception:
            raise CheckPublisherUnavailable("external check polling is unavailable") from None
        results: list[CheckProcessResult] = []
        for event in events:
            try:
                results.append(self.process(event))
            except CheckPublisherUnavailable:
                results.append(
                    CheckProcessResult(
                        schema_version="3.1",
                        state="WAITING_EXTERNAL_CHANNEL",
                        event_id=event.event_id,
                    )
                )
        return results
