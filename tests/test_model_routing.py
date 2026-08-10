from __future__ import annotations

from tcfactory.model_routing import (
    may_downgrade_for_limit,
    routed_stage,
    stage_model_chain,
)
from tcfactory.models import PauseKind, RoleConfig, RoleName, Stage


def _role() -> RoleConfig:
    return RoleConfig(
        prompt_file="prompts/builder.md",
        model="sonnet",
        tools=["Read"],
    )


def test_fable_route_is_ordered_and_deduplicated() -> None:
    stage = Stage(
        role=RoleName.BUILDER,
        model="fable",
        fallback_models=["opus", "sonnet", "opus"],
    )
    chain = stage_model_chain(stage, _role())
    assert chain == ["fable", "opus", "sonnet"]
    assert routed_stage(stage, chain, 1).model == "opus"
    assert routed_stage(stage, chain, 1).fallback_models == []


def test_only_model_specific_limit_can_downgrade() -> None:
    chain = ["fable", "opus", "sonnet"]
    assert may_downgrade_for_limit(PauseKind.MODEL_LIMIT, chain, 0)
    assert not may_downgrade_for_limit(PauseKind.WEEKLY, chain, 0)
    assert not may_downgrade_for_limit(PauseKind.FIVE_HOUR, chain, 0)
    assert not may_downgrade_for_limit(PauseKind.AUTHENTICATION, chain, 0)
    assert not may_downgrade_for_limit(PauseKind.MODEL_LIMIT, chain, 2)


def test_role_fallbacks_apply_when_stage_has_no_override() -> None:
    role = _role().model_copy(update={"fallback_models": ["haiku"]})
    stage = Stage(role=RoleName.BUILDER)
    assert stage_model_chain(stage, role) == ["sonnet", "haiku"]
