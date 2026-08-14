"""TrainCapsule qualification API."""

from .experiment import execute_qualification
from .models import (
    CommandExpectation,
    ExperimentRun,
    ExperimentSpecification,
    NativeBaseline,
    PreflightInputs,
    QualificationDecision,
    QualificationResult,
)
from .qualify import (
    assess_completeness,
    evaluate_preflight,
    generate_native_baseline,
    render_native_baseline_human,
)

__all__ = [
    "NativeBaseline",
    "PreflightInputs",
    "CommandExpectation",
    "ExperimentRun",
    "ExperimentSpecification",
    "QualificationDecision",
    "QualificationResult",
    "assess_completeness",
    "evaluate_preflight",
    "execute_qualification",
    "generate_native_baseline",
    "render_native_baseline_human",
]
