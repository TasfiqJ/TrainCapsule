from __future__ import annotations

from .models import PauseKind, RoleConfig, Stage


def stage_model_chain(stage: Stage, role_config: RoleConfig) -> list[str]:
    """Return the controller-owned primary and ordered subscription fallbacks."""

    primary = stage.model or role_config.model
    configured = stage.fallback_models or role_config.fallback_models
    return list(dict.fromkeys([primary, *configured]))


def routed_stage(stage: Stage, chain: list[str], index: int) -> Stage:
    """Select one model and expose only its remaining availability fallbacks."""

    return stage.model_copy(
        update={
            "model": chain[index],
            "fallback_models": chain[index + 1 :],
        }
    )


def may_downgrade_for_limit(kind: PauseKind, chain: list[str], index: int) -> bool:
    """Only a model-family cap may downgrade; total-plan limits must pause."""

    return kind == PauseKind.MODEL_LIMIT and index + 1 < len(chain)
