from pathlib import Path

from tcfactory.config import load_roles
from tcfactory.models import RoleName
from tcfactory.prompts import compose_system_prompt

ROOT = Path(__file__).resolve().parents[1]


def test_all_claude_owners_receive_dependency_aware_execution_policy() -> None:
    roles = load_roles(ROOT / "config/roles.yaml")
    prompt = compose_system_prompt(
        repo_root=ROOT,
        global_prompt_path="prompts/global.md",
        role=roles[RoleName.BUILDER],
        role_name=RoleName.BUILDER.value,
    )

    assert "## Dependency-aware execution" in prompt
    assert "Keep one mutating owner for the candidate" in prompt
    assert "frozen candidate SHA" in prompt
    assert "taints its dependents" in prompt
    assert "Max quota as a shared resource" in prompt


def test_research_policy_separates_parallel_discovery_from_dependent_verification() -> None:
    prompt = (ROOT / "prompts/research.md").read_text(encoding="utf-8")

    assert "explicit `depends_on` list" in prompt
    assert "query graph must be acyclic" in prompt
    assert "Independent discovery can run" in prompt
    assert "concurrently; verification must use the exact claim" in prompt
    assert "verification must use the exact claim" in prompt
