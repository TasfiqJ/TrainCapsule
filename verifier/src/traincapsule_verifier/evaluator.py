"""Independent, fail-closed policy evaluation and receipt lifecycle."""

from __future__ import annotations

import fnmatch
import hashlib
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import BaseModel, ValidationError

from .canonical import canonical_json_bytes, model_digest, sha256_digest
from .crypto import (
    SignatureError,
    load_private_key,
    load_public_key,
    public_key_fingerprint,
    sign_model,
    verify_model_signature,
)
from .filesystem import (
    NonceStore,
    TrustedPathError,
    TrustedRoot,
    assert_trusted_root,
    atomic_write_new,
    open_trusted_file,
    read_bounded_file,
    sha256_file,
    strict_json_loads,
)
from .models import (
    ActivationReceipt,
    ActivationRequest,
    AuthorityAnchor,
    CheckAuthorization,
    CommercialCeiling,
    EngineeringCeiling,
    EvidenceMode,
    GateResult,
    MachinePolicyReceipt,
    NativeDisposition,
    OracleExecutionResult,
    OracleObservation,
    OracleOutcome,
    PolicyDecision,
    RevocationList,
    TrustedEvidenceManifest,
    ValueDisposition,
    VerificationRequest,
    VerifierPolicy,
)


class VerificationError(RuntimeError):
    pass


_ENGINEERING_RANK = {
    EngineeringCeiling.NOT_EVALUATED: 0,
    EngineeringCeiling.FAILED: 1,
    EngineeringCeiling.PASSED: 2,
}
_COMMERCIAL_RANK = {
    CommercialCeiling.NOT_EVALUATED: 0,
    CommercialCeiling.NATIVE_ADVANTAGE_UNPROVEN: 1,
    CommercialCeiling.PILOT_ELIGIBLE: 2,
    CommercialCeiling.COMMERCIALLY_SUPPORTED: 3,
    CommercialCeiling.WITHDRAWN: 0,
}


def _load_model[T: BaseModel](root: TrustedRoot, relative: str, model: type[T]) -> T:
    raw = read_bounded_file(root, relative)
    strict_json_loads(raw)
    try:
        validator = model.model_validate_json
        return validator(raw)
    except (ValidationError, ValueError) as exc:
        raise VerificationError(f"trusted {relative} contract is invalid") from exc


def verification_request_digest(request: VerificationRequest) -> str:
    payload = request.model_dump(mode="json", by_alias=True, exclude_none=False)
    payload.pop("requestDigest")
    return sha256_digest(canonical_json_bytes(payload))


def _receipt_id(prefix: str, payload: bytes) -> str:
    return f"{prefix}:{sha256_digest(payload).split(':', 1)[1][:32].upper()}"


class IndependentVerifier:
    """Verifier with externally owned policy, state, evidence, and key material."""

    def __init__(
        self,
        *,
        policy: VerifierPolicy,
        revocations: RevocationList,
        signing_key: Ed25519PrivateKey,
        public_key: Ed25519PublicKey,
        anchor: AuthorityAnchor,
        state_root: TrustedRoot,
        receipt_root: TrustedRoot,
        oracle_root: TrustedRoot | None,
    ) -> None:
        self.policy = policy
        self.revocations = revocations
        self.signing_key = signing_key
        self.public_key = public_key
        self.anchor = anchor
        self.state_root = state_root
        self.receipt_root = receipt_root
        self.oracle_root = oracle_root
        self.nonces = NonceStore(state_root)
        self._closed = False
        self._validate_authority()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        seen: set[int] = set()
        for root in (self.state_root, self.receipt_root, self.oracle_root):
            if root is None or id(root) in seen:
                continue
            seen.add(id(root))
            root.close()

    def __enter__(self) -> IndependentVerifier:
        if self._closed:
            raise VerificationError("independent verifier is closed")
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    @classmethod
    def from_external_roots(
        cls,
        *,
        repository_root: Path,
        config_root: Path,
        state_root: Path,
        private_root: Path,
        receipt_root: Path,
        anchor_root: Path,
        oracle_root: Path,
        authority_state_root: Path | None = None,
        config_owner_uid: int = 0,
        verifier_owner_uid: int = 0,
    ) -> IndependentVerifier:
        opened: list[TrustedRoot] = []
        persistent: set[int] = set()
        verifier: IndependentVerifier | None = None
        try:
            config = assert_trusted_root(
                config_root, expected_uid=config_owner_uid, repository_root=repository_root
            )
            opened.append(config)
            state = assert_trusted_root(
                state_root, expected_uid=verifier_owner_uid, repository_root=repository_root
            )
            opened.append(state)
            private = assert_trusted_root(
                private_root, expected_uid=verifier_owner_uid, repository_root=repository_root
            )
            opened.append(private)
            receipts = assert_trusted_root(
                receipt_root, expected_uid=verifier_owner_uid, repository_root=repository_root
            )
            opened.append(receipts)
            anchors = assert_trusted_root(
                anchor_root, expected_uid=config_owner_uid, repository_root=repository_root
            )
            opened.append(anchors)
            authority_state = (
                state
                if authority_state_root is None
                else assert_trusted_root(
                    authority_state_root,
                    expected_uid=config_owner_uid,
                    repository_root=repository_root,
                )
            )
            if authority_state is not state:
                opened.append(authority_state)
            oracles = assert_trusted_root(
                oracle_root, expected_uid=config_owner_uid, repository_root=repository_root
            )
            opened.append(oracles)
            policy = _load_model(config, "policy.json", VerifierPolicy)
            revocations = _load_model(authority_state, "revocations.json", RevocationList)
            anchor = _load_model(anchors, "authority-anchor.json", AuthorityAnchor)
            public_key = load_public_key(
                read_bounded_file(config, "public-key.pem", maximum_bytes=8192)
            )
            signing_key = load_private_key(
                read_bounded_file(
                    private,
                    "signing-key.pem",
                    maximum_bytes=8192,
                    required_mode=0o600,
                )
            )
            verifier = cls(
                policy=policy,
                revocations=revocations,
                signing_key=signing_key,
                public_key=public_key,
                anchor=anchor,
                state_root=state,
                receipt_root=receipts,
                oracle_root=oracles,
            )
            persistent = {id(state), id(receipts), id(oracles)}
            return verifier
        finally:
            for root in reversed(opened):
                if verifier is None or id(root) not in persistent:
                    root.close()

    def _validate_authority(self) -> None:
        if public_key_fingerprint(self.public_key) != self.policy.public_key_fingerprint:
            raise VerificationError("public key fingerprint does not match active policy")
        try:
            verify_model_signature(self.revocations, self.public_key)
        except SignatureError as exc:
            raise VerificationError("revocation list signature is invalid") from exc
        if (
            self.revocations.policy_id != self.policy.policy_id
            or self.revocations.policy_version != self.policy.policy_version
            or self.revocations.issuer_id != self.policy.issuer_id
            or self.revocations.issuer_key_id != self.policy.issuer_key_id
        ):
            raise VerificationError("revocation list authority does not match policy")
        if self.revocations.revocation_epoch < self.policy.minimum_revocation_epoch:
            raise VerificationError("revocation list epoch is below active policy minimum")
        expected_anchor = (
            (self.anchor.policy_id, self.policy.policy_id),
            (self.anchor.policy_version, self.policy.policy_version),
            (self.anchor.issuer_id, self.policy.issuer_id),
            (self.anchor.issuer_key_id, self.policy.issuer_key_id),
            (self.anchor.public_key_fingerprint, self.policy.public_key_fingerprint),
            (self.anchor.revocation_epoch, self.revocations.revocation_epoch),
            (self.anchor.revocation_list_digest, model_digest(self.revocations)),
            (
                self.anchor.previous_revocation_list_digest,
                self.revocations.previous_list_digest,
            ),
        )
        if any(observed != expected for observed, expected in expected_anchor):
            raise VerificationError("authority state does not match monotonic external anchor")

    def issue_receipt(
        self,
        request: VerificationRequest,
        *,
        evidence_root: Path,
        repository_root: Path,
        evidence_owner_uid: int = 0,
        now: datetime | None = None,
    ) -> MachinePolicyReceipt:
        observed_now = (now or datetime.now(UTC)).astimezone(UTC)
        try:
            request = VerificationRequest.model_validate(
                request.model_dump(mode="python", by_alias=True), strict=True
            )
        except ValidationError as exc:
            raise VerificationError("verification request contract is invalid") from exc
        self._validate_revocation_freshness(observed_now)
        with assert_trusted_root(
            evidence_root,
            expected_uid=evidence_owner_uid,
            repository_root=repository_root,
        ) as trusted_evidence:
            evidence = _load_model(trusted_evidence, "evidence.json", TrustedEvidenceManifest)
            raw_hashes = self._evaluate(request, evidence, trusted_evidence, observed_now)
        self.nonces.consume(request.nonce)
        lifetime = timedelta(seconds=self.policy.maximum_receipt_lifetime_seconds)
        receipt_payload = self._receipt_payload(
            request, evidence, raw_hashes, observed_now, observed_now + lifetime
        )
        placeholder = "A" * 88
        provisional = MachinePolicyReceipt.model_validate(
            {**receipt_payload, "signature": placeholder}, strict=True
        )
        receipt = provisional.model_copy(
            update={"signature": sign_model(provisional, self.signing_key)}
        )
        verified = MachinePolicyReceipt.model_validate(
            receipt.model_dump(mode="python", by_alias=True), strict=True
        )
        verify_model_signature(verified, self.public_key)
        atomic_write_new(
            self.receipt_root,
            f"{verified.receipt_id}.json",
            canonical_json_bytes(verified),
        )
        return verified

    def _evaluate(
        self,
        request: VerificationRequest,
        evidence: TrustedEvidenceManifest,
        evidence_root: TrustedRoot,
        now: datetime,
    ) -> list[str]:
        if request.request_digest != verification_request_digest(request):
            raise VerificationError("request digest does not authenticate exact request fields")
        if request.source_generation_id != self.policy.active_source_generation_id or (
            request.source_generation_digest != self.policy.active_source_generation_digest
        ):
            raise VerificationError("request uses the wrong source generation")
        exact_fields = (
            "candidate_sha",
            "work_item_id",
            "milestone_id",
            "lane",
            "candidate_tree_sha",
            "base_sha",
            "source_generation_id",
            "source_generation_digest",
            "context_manifest_digest",
            "task_packet_digest",
            "candidate_manifest_digest",
            "checkpoint_digest",
        )
        for field in exact_fields:
            if getattr(request, field) != getattr(evidence, field):
                raise VerificationError(f"trusted evidence {field} mismatch")
        age = now - evidence.observed_at.astimezone(UTC)
        if (
            age < -timedelta(minutes=5)
            or age.total_seconds() > self.policy.maximum_evidence_age_seconds
        ):
            raise VerificationError("trusted evidence is future-dated or stale")
        risk = self.policy.risk_policies.get(request.risk_tier)
        if risk is None:
            raise VerificationError("request risk tier is not covered by policy")
        if evidence.evidence_mode not in risk.accepted_evidence_modes:
            raise VerificationError("evidence mode is not accepted for this risk tier")
        if (
            evidence.private_gate_suite_id != self.policy.private_gate_suite_id
            or evidence.private_gate_runner_digest != self.policy.private_gate_runner_digest
        ):
            raise VerificationError("private gate suite or runner mismatch")
        missing_gates = set(risk.required_gates) - set(evidence.gates)
        if missing_gates:
            raise VerificationError(f"required gates are missing: {sorted(missing_gates)}")
        if any(gate.result is not GateResult.PASS for gate in evidence.gates.values()):
            raise VerificationError("all observed gates must pass")
        computed_hashes: list[str] = []
        for binding in evidence.raw_artifacts.values():
            observed = sha256_file(evidence_root, binding.path)
            if observed != binding.digest:
                raise VerificationError("raw evidence artifact digest mismatch")
            computed_hashes.append(observed)
        if len(computed_hashes) != len(set(computed_hashes)):
            raise VerificationError("raw evidence artifact hashes must be unique")
        for identifier, oracle in evidence.oracles.items():
            if oracle.oracle_runner_digest != risk.oracle_runner_digests.get(identifier):
                raise VerificationError("independent oracle runner digest mismatch")
        observed_oracles, oracle_output_hashes = self._execute_oracles(
            request=request,
            evidence=evidence,
            artifact_hashes=sorted(computed_hashes),
        )
        if observed_oracles != evidence.oracles:
            raise VerificationError("trusted oracle manifest differs from independent execution")
        computed_hashes.extend(oracle_output_hashes)
        oracle_hashes = {
            digest
            for oracle in evidence.oracles.values()
            for digest in oracle.raw_evidence_artifact_hashes
        }
        if oracle_hashes != {binding.digest for binding in evidence.raw_artifacts.values()}:
            raise VerificationError("oracle/raw evidence artifact set mismatch")
        gate_hashes = {gate.evidence_digest for gate in evidence.gates.values()}
        if not gate_hashes <= set(computed_hashes):
            raise VerificationError("gate evidence digest is not bound to a raw artifact")
        self._evaluate_claims_scope_and_dispositions(request, evidence)
        return sorted(computed_hashes)

    def _execute_oracles(
        self,
        *,
        request: VerificationRequest,
        evidence: TrustedEvidenceManifest,
        artifact_hashes: list[str],
    ) -> tuple[dict[str, OracleObservation], list[str]]:
        if self.oracle_root is None:
            raise VerificationError("independent oracle root is unavailable")
        risk = self.policy.risk_policies[request.risk_tier]
        if set(evidence.oracles) != set(risk.required_oracle_ids):
            raise VerificationError("independent oracle identity set mismatch")
        observed: dict[str, OracleObservation] = {}
        output_hashes: list[str] = []
        for identifier in sorted(risk.required_oracle_ids):
            runner_path = risk.oracle_runner_paths[identifier]
            descriptor = open_trusted_file(
                self.oracle_root,
                runner_path,
                maximum_bytes=5_000_000,
                require_executable=True,
            )
            try:
                runner_bytes = bytearray()
                while True:
                    chunk = os.read(descriptor, 1_048_576)
                    if not chunk:
                        break
                    runner_bytes.extend(chunk)
                    if len(runner_bytes) > 5_000_000:
                        raise VerificationError("independent oracle runner exceeds size limit")
                observed_runner_digest = "sha256:" + hashlib.sha256(runner_bytes).hexdigest()
                if observed_runner_digest != risk.oracle_runner_digests[identifier]:
                    raise VerificationError("independent oracle runner digest mismatch")
                payload = canonical_json_bytes(
                    {
                        "schemaVersion": "3.1",
                        "oracleId": identifier,
                        "candidateSha": request.candidate_sha,
                        "candidateTreeSha": request.candidate_tree_sha,
                        "baseSha": request.base_sha,
                        "workItemId": request.work_item_id,
                        "milestoneId": request.milestone_id,
                        "lane": request.lane,
                        "evidenceMode": evidence.evidence_mode,
                        "rawEvidenceArtifactHashes": artifact_hashes,
                    }
                )
                process = subprocess.run(
                    [f"/proc/self/fd/{descriptor}"],
                    input=payload,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=30,
                    env={"LANG": "C", "LC_ALL": "C"},
                    pass_fds=(descriptor,),
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise VerificationError("independent oracle execution failed") from exc
            finally:
                os.close(descriptor)
            if process.returncode != 0 or len(process.stdout) > 1_000_000:
                raise VerificationError("independent oracle execution failed")
            strict_json_loads(process.stdout)
            try:
                result = OracleExecutionResult.model_validate_json(process.stdout)
            except (ValidationError, ValueError) as exc:
                raise VerificationError("independent oracle result is invalid") from exc
            oracle = OracleObservation(
                oracle_id=identifier,
                oracle_runner_digest=observed_runner_digest,
                candidate_sha=request.candidate_sha,
                candidate_tree_sha=request.candidate_tree_sha,
                outcome=result.outcome,
                raw_evidence_artifact_hashes=result.raw_evidence_artifact_hashes,
                native_disposition=result.native_disposition,
                value_disposition=result.value_disposition,
                engineering_ceiling=result.engineering_ceiling,
                commercial_ceiling=result.commercial_ceiling,
            )
            if oracle.outcome is not OracleOutcome.PASS:
                raise VerificationError("independent oracle did not pass")
            observed[identifier] = oracle
            output_hashes.append(sha256_digest(process.stdout))
        return observed, output_hashes

    def _evaluate_claims_scope_and_dispositions(
        self, request: VerificationRequest, evidence: TrustedEvidenceManifest
    ) -> None:
        requested = set(request.requested_claims)
        if not requested <= set(self.policy.allowed_claims):
            raise VerificationError("request contains a claim not allowed by policy")
        if requested & set(self.policy.forbidden_claims):
            raise VerificationError("request contains a forbidden claim")
        for path in request.publication_scope:
            if not any(
                fnmatch.fnmatchcase(path, allowed)
                for allowed in self.policy.allowed_publication_scopes
            ):
                raise VerificationError("publication scope escapes active policy")
        oracle_values = list(evidence.oracles.values())
        expected = (
            (request.native_substitute_disposition, "native_disposition"),
            (request.decision_value_disposition, "value_disposition"),
            (request.engineering_maturity_ceiling, "engineering_ceiling"),
            (request.commercial_maturity_ceiling, "commercial_ceiling"),
        )
        for requested_value, attribute in expected:
            if any(getattr(oracle, attribute) != requested_value for oracle in oracle_values):
                raise VerificationError(f"oracle consensus rejects requested {attribute}")
        risk = self.policy.risk_policies[request.risk_tier]
        if (
            _ENGINEERING_RANK[request.engineering_maturity_ceiling]
            > _ENGINEERING_RANK[risk.maximum_engineering_ceiling]
            or _COMMERCIAL_RANK[request.commercial_maturity_ceiling]
            > _COMMERCIAL_RANK[risk.maximum_commercial_ceiling]
        ):
            raise VerificationError("requested maturity exceeds policy ceiling")
        if request.commercial_maturity_ceiling is CommercialCeiling.COMMERCIALLY_SUPPORTED and (
            evidence.evidence_mode is not EvidenceMode.LIVE_VALIDATED
            or request.decision_value_disposition
            is not ValueDisposition.INCREMENTAL_DECISION_VALUE_DEMONSTRATED
        ):
            raise VerificationError("commercial support lacks live incremental-value proof")
        if (
            request.native_substitute_disposition is NativeDisposition.NATIVE_SUFFICIENT
            and request.decision_value_disposition
            is not ValueDisposition.NATIVE_WORKFLOW_SUFFICIENT
        ):
            raise VerificationError("native sufficiency and value disposition disagree")

    def _receipt_payload(
        self,
        request: VerificationRequest,
        evidence: TrustedEvidenceManifest,
        raw_hashes: list[str],
        issued_at: datetime,
        expires_at: datetime,
    ) -> dict[str, object]:
        identity = canonical_json_bytes(
            {
                "requestDigest": request.request_digest,
                "nonce": request.nonce,
                "issuedAt": issued_at.isoformat(),
            }
        )
        return {
            "schemaVersion": "3.1",
            "receiptId": _receipt_id("MPOL", identity),
            "policyId": self.policy.policy_id,
            "policyVersion": self.policy.policy_version,
            "issuerId": self.policy.issuer_id,
            "issuerKeyId": self.policy.issuer_key_id,
            "issuedAt": issued_at,
            "expiresAt": expires_at,
            "revocationEpoch": self.revocations.revocation_epoch,
            "nonce": request.nonce,
            "requestDigest": request.request_digest,
            "workItemId": request.work_item_id,
            "milestoneId": request.milestone_id,
            "lane": request.lane,
            "riskTier": request.risk_tier,
            "candidateSha": request.candidate_sha,
            "candidateTreeSha": request.candidate_tree_sha,
            "baseSha": request.base_sha,
            "sourceGenerationId": request.source_generation_id,
            "sourceGenerationDigest": request.source_generation_digest,
            "contextManifestDigest": request.context_manifest_digest,
            "taskPacketDigest": request.task_packet_digest,
            "candidateManifestDigest": request.candidate_manifest_digest,
            "checkpointDigest": request.checkpoint_digest,
            "requiredGateResults": {
                name: gate.result for name, gate in sorted(evidence.gates.items())
            },
            "privateGateSuiteId": evidence.private_gate_suite_id,
            "privateGateRunnerDigest": evidence.private_gate_runner_digest,
            "independentOracleIds": sorted(evidence.oracles),
            "rawEvidenceArtifactHashes": raw_hashes,
            "nativeSubstituteDisposition": request.native_substitute_disposition,
            "decisionValueDisposition": request.decision_value_disposition,
            "engineeringMaturityCeiling": request.engineering_maturity_ceiling,
            "commercialMaturityCeiling": request.commercial_maturity_ceiling,
            "allowedClaims": request.requested_claims,
            "forbiddenClaims": self.policy.forbidden_claims,
            "publicationScope": request.publication_scope,
            "decision": PolicyDecision.PASS,
            "signatureAlgorithm": "ed25519",
        }

    def verify_receipt(
        self,
        receipt: MachinePolicyReceipt,
        *,
        request: VerificationRequest | None = None,
        now: datetime | None = None,
    ) -> None:
        observed_now = (now or datetime.now(UTC)).astimezone(UTC)
        try:
            receipt = MachinePolicyReceipt.model_validate(
                receipt.model_dump(mode="python", by_alias=True), strict=True
            )
        except ValidationError as exc:
            raise VerificationError("machine-policy receipt contract is invalid") from exc
        self._validate_revocation_freshness(observed_now)
        try:
            verify_model_signature(receipt, self.public_key)
        except SignatureError as exc:
            raise VerificationError("machine-policy receipt signature is invalid") from exc
        if (
            receipt.policy_id != self.policy.policy_id
            or receipt.policy_version != self.policy.policy_version
            or receipt.issuer_id != self.policy.issuer_id
            or receipt.issuer_key_id != self.policy.issuer_key_id
        ):
            raise VerificationError("receipt authority or policy version mismatch")
        if receipt.expires_at.astimezone(UTC) <= observed_now:
            raise VerificationError("machine-policy receipt is expired")
        if receipt.issued_at.astimezone(UTC) > observed_now + timedelta(minutes=5):
            raise VerificationError("machine-policy receipt is future-dated")
        self._reject_revoked(receipt)
        if request is not None:
            expected = (
                ("request_digest", request.request_digest),
                ("nonce", request.nonce),
                ("work_item_id", request.work_item_id),
                ("milestone_id", request.milestone_id),
                ("lane", request.lane),
                ("risk_tier", request.risk_tier),
                ("candidate_sha", request.candidate_sha),
                ("candidate_tree_sha", request.candidate_tree_sha),
                ("base_sha", request.base_sha),
                ("source_generation_id", request.source_generation_id),
                ("source_generation_digest", request.source_generation_digest),
                ("context_manifest_digest", request.context_manifest_digest),
                ("task_packet_digest", request.task_packet_digest),
                ("candidate_manifest_digest", request.candidate_manifest_digest),
                ("checkpoint_digest", request.checkpoint_digest),
            )
            for field, value in expected:
                if getattr(receipt, field) != value:
                    raise VerificationError(f"receipt {field} does not match request")

    def _reject_revoked(self, receipt: MachinePolicyReceipt) -> None:
        if self.revocations.revocation_epoch < receipt.revocation_epoch:
            raise VerificationError("revocation state is older than receipt")
        if (
            receipt.receipt_id in self.revocations.revoked_receipt_ids
            or receipt.nonce in self.revocations.revoked_nonces
            or receipt.issuer_key_id in self.revocations.revoked_key_ids
        ):
            raise VerificationError("machine-policy receipt is revoked")

    def _validate_revocation_freshness(self, now: datetime) -> None:
        if self._closed:
            raise VerificationError("independent verifier is closed")
        if self.revocations.issued_at.astimezone(UTC) > now + timedelta(minutes=5):
            raise VerificationError("revocation list is future-dated")
        if self.revocations.expires_at.astimezone(UTC) <= now:
            raise VerificationError("revocation list is expired")

    def _require_local_receipt(self, receipt: MachinePolicyReceipt) -> None:
        relative = f"{receipt.receipt_id}.json"
        try:
            observed = read_bounded_file(self.receipt_root, relative)
        except (OSError, TrustedPathError) as exc:
            raise VerificationError("matching local signed receipt is unavailable") from exc
        if observed != canonical_json_bytes(receipt):
            raise VerificationError("matching local signed receipt bytes differ")

    def authorize_check(
        self, receipt: MachinePolicyReceipt, *, now: datetime | None = None
    ) -> CheckAuthorization:
        self.verify_receipt(receipt, now=now)
        self._require_local_receipt(receipt)
        return CheckAuthorization(
            schema_version="3.1",
            check_name="TrainCapsule / Machine policy",
            candidate_sha=receipt.candidate_sha,
            conclusion="success",
            receipt_id=receipt.receipt_id,
            receipt_digest=model_digest(receipt),
        )

    def issue_activation(
        self,
        request: ActivationRequest,
        *,
        observed_main_sha: str,
        activation_root: Path,
        repository_root: Path,
        activation_owner_uid: int = 0,
        now: datetime | None = None,
    ) -> ActivationReceipt:
        observed_now = (now or datetime.now(UTC)).astimezone(UTC)
        try:
            request = ActivationRequest.model_validate(
                request.model_dump(mode="python", by_alias=True), strict=True
            )
        except ValidationError as exc:
            raise VerificationError("activation request contract is invalid") from exc
        self._validate_revocation_freshness(observed_now)
        self.verify_receipt(request.machine_policy_receipt, now=observed_now)
        self._require_local_receipt(request.machine_policy_receipt)
        if observed_main_sha != request.verified_main_sha:
            raise VerificationError("activation main SHA does not match observed main")
        if request.machine_policy_receipt.candidate_sha != request.verified_main_sha:
            raise VerificationError("activation main SHA does not match policy receipt")
        if (
            request.source_generation_id != self.policy.active_source_generation_id
            or request.source_generation_digest != self.policy.active_source_generation_digest
        ):
            raise VerificationError("activation source generation mismatch")
        with assert_trusted_root(
            activation_root,
            expected_uid=activation_owner_uid,
            repository_root=repository_root,
        ) as trusted_activation:
            observed_artifacts = {
                "machine environment": (
                    sha256_file(trusted_activation, request.machine_environment_path),
                    request.machine_environment_digest,
                ),
                "controller binary": (
                    sha256_file(trusted_activation, request.controller_binary_path),
                    request.controller_binary_digest,
                ),
                "controller config": (
                    sha256_file(trusted_activation, request.controller_config_path),
                    request.controller_config_digest,
                ),
            }
        for label, (observed, expected) in observed_artifacts.items():
            if observed != expected:
                raise VerificationError(f"activation {label} digest mismatch")
        self.nonces.consume(request.nonce)
        expires = observed_now + timedelta(
            seconds=min(self.policy.maximum_receipt_lifetime_seconds, 3600)
        )
        payload: dict[str, object] = {
            "schemaVersion": "3.1",
            "receiptId": _receipt_id("ACT", canonical_json_bytes(request)),
            "verifiedMainSha": request.verified_main_sha,
            "machineEnvironmentDigest": request.machine_environment_digest,
            "sourceGenerationId": request.source_generation_id,
            "sourceGenerationDigest": request.source_generation_digest,
            "controllerBinaryDigest": request.controller_binary_digest,
            "controllerConfigDigest": request.controller_config_digest,
            "machineEnvironmentPath": request.machine_environment_path,
            "controllerBinaryPath": request.controller_binary_path,
            "controllerConfigPath": request.controller_config_path,
            "machinePolicyReceiptId": request.machine_policy_receipt.receipt_id,
            "machinePolicyReceiptDigest": model_digest(request.machine_policy_receipt),
            "mode": request.mode,
            "issuedAt": observed_now,
            "expiresAt": expires,
            "revocationEpoch": self.revocations.revocation_epoch,
            "nonce": request.nonce,
            "issuerId": self.policy.issuer_id,
            "issuerKeyId": self.policy.issuer_key_id,
            "signatureAlgorithm": "ed25519",
            "signature": "A" * 88,
        }
        provisional = ActivationReceipt.model_validate(payload, strict=True)
        receipt = provisional.model_copy(
            update={"signature": sign_model(provisional, self.signing_key)}
        )
        verify_model_signature(receipt, self.public_key)
        atomic_write_new(
            self.receipt_root,
            f"{receipt.receipt_id}.json",
            canonical_json_bytes(receipt),
        )
        return receipt

    def verify_activation(
        self,
        receipt: ActivationReceipt,
        *,
        observed_main_sha: str,
        machine_policy_receipt: MachinePolicyReceipt,
        activation_root: Path,
        repository_root: Path,
        activation_owner_uid: int = 0,
        now: datetime | None = None,
    ) -> None:
        observed_now = (now or datetime.now(UTC)).astimezone(UTC)
        try:
            receipt = ActivationReceipt.model_validate(
                receipt.model_dump(mode="python", by_alias=True), strict=True
            )
        except ValidationError as exc:
            raise VerificationError("activation receipt contract is invalid") from exc
        self._validate_revocation_freshness(observed_now)
        try:
            verify_model_signature(receipt, self.public_key)
        except SignatureError as exc:
            raise VerificationError("activation receipt signature is invalid") from exc
        if receipt.expires_at <= observed_now:
            raise VerificationError("activation receipt is expired")
        if receipt.issued_at > observed_now + timedelta(minutes=5):
            raise VerificationError("activation receipt is future-dated")
        self.verify_receipt(machine_policy_receipt, now=observed_now)
        self._require_local_receipt(machine_policy_receipt)
        if (
            receipt.machine_policy_receipt_id != machine_policy_receipt.receipt_id
            or receipt.machine_policy_receipt_digest != model_digest(machine_policy_receipt)
        ):
            raise VerificationError("activation linked policy receipt mismatch")
        with assert_trusted_root(
            activation_root,
            expected_uid=activation_owner_uid,
            repository_root=repository_root,
        ) as trusted_activation:
            observed_digests = {
                "machine_environment_digest": sha256_file(
                    trusted_activation, receipt.machine_environment_path
                ),
                "controller_binary_digest": sha256_file(
                    trusted_activation, receipt.controller_binary_path
                ),
                "controller_config_digest": sha256_file(
                    trusted_activation, receipt.controller_config_path
                ),
            }
        expected = {
            "verified_main_sha": observed_main_sha,
            **observed_digests,
            "source_generation_id": self.policy.active_source_generation_id,
            "source_generation_digest": self.policy.active_source_generation_digest,
            "issuer_id": self.policy.issuer_id,
            "issuer_key_id": self.policy.issuer_key_id,
        }
        for field, value in expected.items():
            if getattr(receipt, field) != value:
                raise VerificationError(f"activation {field} mismatch")
        if receipt.revocation_epoch > self.revocations.revocation_epoch:
            raise VerificationError("activation revocation state is stale")
        if (
            receipt.receipt_id in self.revocations.revoked_receipt_ids
            or receipt.nonce in self.revocations.revoked_nonces
            or receipt.issuer_key_id in self.revocations.revoked_key_ids
        ):
            raise VerificationError("activation receipt is revoked")
