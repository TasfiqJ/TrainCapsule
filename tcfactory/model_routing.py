from __future__ import annotations

from .models import PauseKind, RoleConfig, Stage


def stage_model_chain(stage: Stage, role_config: RoleConfig) -> list[str]:
    """Return the controller-owned primary and ordered subscription fallbacks."""

    primary = stage.model or role_config.model
    configured = stage.fallback_models or role_config.fallback_models
    return list(dict.fromkeys([primary, *configured]))


def routed_stage(stage: Stage, chain: list[str], index: int) -> Stage:
    """Select exactly one model; the controller owns ordered fallback routing."""

    return stage.model_copy(
        update={
            "model": chain[index],
            # ClaudeAgentOptions accepts only one fallback model.  Supplying the
            # remainder as a comma-separated alias hides which model actually ran
            # and can retry a model twice.  The pipeline advances ``chain`` only
            # after a machine-attributed model-limit event, so keep the SDK route
            # single-model and observable.
            "fallback_models": [],
        }
    )


def may_downgrade_for_limit(kind: PauseKind, chain: list[str], index: int) -> bool:
    """Only a model-family cap may downgrade; total-plan limits must pause."""

    return kind == PauseKind.MODEL_LIMIT and index + 1 < len(chain)
