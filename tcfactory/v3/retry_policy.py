"""Finite retry and repeated-finding policy."""

from pydantic import Field

from tcfactory.v3.base import V3Model


class RetryPolicy(V3Model):
    """Zero means no attempts; it never means unlimited."""

    max_plan_attempts: int = Field(ge=0, le=5)
    max_candidate_repair_cycles: int = Field(ge=0, le=10)
    max_same_finding_repeats: int = Field(default=2, ge=1, le=5)
    max_candidate_restarts: int = Field(default=1, ge=0, le=3)

    def plan_attempts_remaining(self, attempts: int) -> int:
        if attempts < 0:
            raise ValueError("attempt count cannot be negative")
        return max(0, self.max_plan_attempts - attempts)

    def repair_cycles_remaining(self, cycles: int) -> int:
        if cycles < 0:
            raise ValueError("cycle count cannot be negative")
        return max(0, self.max_candidate_repair_cycles - cycles)

    def repeated_finding_exhausted(self, repeats: int) -> bool:
        if repeats < 0:
            raise ValueError("repeat count cannot be negative")
        return repeats >= self.max_same_finding_repeats
