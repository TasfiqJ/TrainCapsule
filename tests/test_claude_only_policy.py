from __future__ import annotations

from pathlib import Path

from tcfactory.config import load_roles
from tcfactory.risk import load_risk_profiles

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_MODELS = {"haiku", "sonnet", "opus"}


def test_active_roles_use_only_claude_aliases() -> None:
    roles = load_roles(ROOT / "config" / "roles.yaml")
    assert {role.model for role in roles.values()} <= ALLOWED_MODELS


def test_risk_profiles_never_select_non_claude_or_fable() -> None:
    raw = load_risk_profiles(ROOT / "config" / "risk_profiles.yaml")
    observed: set[str] = set()
    for profile in raw["profiles"].values():
        for role in profile["roles"].values():
            observed.add(str(role["model"]))
    assert observed <= ALLOWED_MODELS
    assert "fable" not in observed


def test_token_routing_reserves_opus_for_risk() -> None:
    raw = load_risk_profiles(ROOT / "config" / "risk_profiles.yaml")
    mechanical = raw["profiles"]["mechanical"]["roles"]
    standard = raw["profiles"]["standard"]["roles"]
    integration = raw["profiles"]["integration"]["roles"]
    trust = raw["profiles"]["trust_core"]["roles"]
    assert mechanical["planner"]["model"] == "haiku"
    assert mechanical["builder"]["model"] == "sonnet"
    assert all(role["model"] == "sonnet" for name, role in standard.items() if name != "security")
    assert integration["builder"]["model"] == "sonnet"
    assert integration["specification"]["model"] == "opus"
    assert integration["adversary"]["model"] == "opus"
    assert trust["builder"]["model"] == "sonnet"
    assert trust["specification"]["model"] == "opus"
    assert trust["release"]["model"] == "sonnet"
