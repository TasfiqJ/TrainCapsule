"""Independent TrainCapsule V3.1-ZH verifier.

The package deliberately has no dependency on the TrainCapsule factory implementation.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .evaluator import IndependentVerifier, VerificationError
from .models import (
    ActivationAuthorization,
    ActivationReceipt,
    ActivationRequest,
    AuthorityAnchor,
    MachinePolicyReceipt,
    OracleExecutionResult,
    RevocationList,
    TrustedEvidenceManifest,
    VerificationRequest,
    VerifierPolicy,
)
from .public_verifier import PublicVerificationError, PublicVerifier


def __getattr__(name: str) -> object:
    """Keep issuer code out of the public verification process unless explicitly requested."""

    if name in {"IndependentVerifier", "VerificationError"}:
        from .evaluator import IndependentVerifier, VerificationError

        return {
            "IndependentVerifier": IndependentVerifier,
            "VerificationError": VerificationError,
        }[name]
    raise AttributeError(name)

__all__ = [
    "ActivationAuthorization",
    "ActivationReceipt",
    "ActivationRequest",
    "AuthorityAnchor",
    "IndependentVerifier",
    "MachinePolicyReceipt",
    "OracleExecutionResult",
    "PublicVerificationError",
    "PublicVerifier",
    "RevocationList",
    "TrustedEvidenceManifest",
    "VerificationError",
    "VerificationRequest",
    "VerifierPolicy",
]
