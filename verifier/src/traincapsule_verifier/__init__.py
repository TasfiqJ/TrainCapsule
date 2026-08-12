"""Independent TrainCapsule V3.1-ZH verifier.

The package deliberately has no dependency on the TrainCapsule factory implementation.
"""

from .evaluator import IndependentVerifier, VerificationError
from .models import (
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

__all__ = [
    "ActivationReceipt",
    "ActivationRequest",
    "AuthorityAnchor",
    "IndependentVerifier",
    "MachinePolicyReceipt",
    "OracleExecutionResult",
    "RevocationList",
    "TrustedEvidenceManifest",
    "VerificationError",
    "VerificationRequest",
    "VerifierPolicy",
]
