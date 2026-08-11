from __future__ import annotations

from pathlib import Path

from tcfactory.config import load_roles
from tcfactory.risk import load_risk_profiles

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_MODELS = {"sonnet", "opus", "fable"}


def test_active_roles_use_only_claude_aliases() -> None:
    roles = load_roles(ROOT / "config" / "roles.yaml")
    assert {role.model for role in roles.values()} <= ALLOWED_MODELS
    assert all(role.task_budget_tokens is None for role in roles.values())


def test_risk_profiles_use_only_subscription_model_aliases() -> None:
    raw = load_risk_profiles(ROOT / "config" / "risk_profiles.yaml")
    observed: set[str] = set()
    for profile in raw["profiles"].values():
        for role in profile["roles"].values():
            observed.add(str(role["model"]))
            observed.update(str(model) for model in role.get("fallback_models", []))
    assert observed <= ALLOWED_MODELS


def test_fable_is_reserved_for_trust_core_builder_with_bounded_fallbacks() -> None:
    raw = load_risk_profiles(ROOT / "config" / "risk_profiles.yaml")
    fable_routes: list[tuple[str, str, dict[str, object]]] = []
    for profile_name, profile in raw["profiles"].items():
        for role_name, role in profile["roles"].items():
            if role["model"] == "fable":
                fable_routes.append((profile_name, role_name, role))
    assert len(fable_routes) == 1
    profile_name, role_name, route = fable_routes[0]
    assert (profile_name, role_name) == ("trust_core", "builder")
    assert route["fallback_models"] == ["opus", "sonnet"]
    assert route["effort"] == "high"
    assert route["max_turns"] == 20
    assert route["task_budget_tokens"] == 72_000


def test_token_routing_reserves_opus_for_risk() -> None:
    raw = load_risk_profiles(ROOT / "config" / "risk_profiles.yaml")
    mechanical = raw["profiles"]["mechanical"]["roles"]
    standard = raw["profiles"]["standard"]["roles"]
    integration = raw["profiles"]["integration"]["roles"]
    trust = raw["profiles"]["trust_core"]["roles"]
    assert mechanical["planner"]["model"] == "sonnet"
    assert mechanical["builder"]["model"] == "sonnet"
    assert all(role["model"] == "sonnet" for name, role in standard.items() if name != "security")
    assert integration["builder"]["model"] == "sonnet"
    assert integration["specification"]["model"] == "opus"
    assert integration["adversary"]["model"] == "opus"
    assert trust["builder"]["model"] == "fable"
    assert trust["builder"]["fallback_models"] == ["opus", "sonnet"]
    assert trust["specification"]["model"] == "opus"
    assert trust["release"]["model"] == "sonnet"
