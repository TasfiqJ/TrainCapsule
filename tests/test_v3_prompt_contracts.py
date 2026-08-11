from pathlib import Path

from tcfactory.config import load_roles

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "prompts"


def _text(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


def test_required_v3_prompt_set_exists() -> None:
    required = {
        "native_substitute_reviewer.md",
        "commercial_experiment.md",
        "human_approval_packet.md",
        "wedge_reviewer.md",
        "milestone_auditor.md",
    }
    assert required.issubset({path.name for path in PROMPTS.glob("*.md")})


def test_global_prompt_holds_normative_v3_execution_contract() -> None:
    prompt = _text("global.md")
    required = {
        "No more than 12 acceptance criteria",
        "No more than 8 declared outputs",
        "NATIVE_WORKFLOW_SUFFICIENT",
        "NO_INCREMENTAL_DECISION_VALUE",
        "UNKNOWN is valid",
        "WAITING_EXTERNAL",
        "WAITING_HUMAN",
        "Return at most 8 findings total",
        "fingerprint:",
        "Do not expand the packet",
        "must not influence routine product or factory work",
        "Do not renew the session",
        "draft pull request",
    }
    assert all(item in prompt for item in required)
    assert "work until done" not in prompt.lower()


def test_planning_prompts_are_finite_and_cannot_mutate_roadmap() -> None:
    for name in ("autonomous_planner.md", "task_packet_planner.md"):
        prompt = _text(name)
        assert "12 acceptance criteria" in prompt
        assert "8" in prompt and "outputs" in prompt
        assert "native" in prompt.lower()
        assert "UNKNOWN" in prompt
        assert "WAITING_HUMAN" in prompt
        assert "roadmap" in prompt.lower()
        assert "work until done" not in prompt.lower()


def test_active_role_limits_are_explicit_and_finite() -> None:
    roles = load_roles(ROOT / "config/roles.yaml")
    assert roles
    for role in roles.values():
        assert 1 <= role.max_turns <= 64
        assert 0 < role.max_budget_usd <= 12.0
        assert role.task_budget_tokens is not None
        assert 1 <= role.task_budget_tokens <= 96_000


def test_read_only_review_prompts_bound_findings_and_truth() -> None:
    reviewers = {
        "integration_scout.md",
        "adversary.md",
        "audit.md",
        "security.md",
        "performance.md",
        "value_validator.md",
        "value_adversary.md",
        "release.md",
        "native_substitute_reviewer.md",
        "wedge_reviewer.md",
        "milestone_auditor.md",
    }
    for name in reviewers:
        prompt = _text(name)
        assert "read-only" in prompt.lower()
        assert "UNKNOWN" in prompt
        assert "at most 8" in prompt.lower()
        assert "roadmap" in prompt.lower()


def test_specialist_prompts_preserve_external_and_human_authority() -> None:
    native = _text("native_substitute_reviewer.md")
    assert "NATIVE_WORKFLOW_SUFFICIENT" in native
    assert "NO_INCREMENTAL_DECISION_VALUE" in native

    commercial = _text("commercial_experiment.md")
    assert "SYNTHETIC_TEST_ONLY" in commercial
    assert "WAITING_EXTERNAL" in commercial
    assert "WAITING_HUMAN" in commercial

    approval = _text("human_approval_packet.md")
    assert "candidate SHA" in approval
    assert "artifact digests" in approval
    assert "Do not approve" in approval
    assert "WAITING_HUMAN" in approval


def test_every_active_role_prompt_exists() -> None:
    for role in load_roles(ROOT / "config/roles.yaml").values():
        prompt_path = ROOT / role.prompt_file
        assert prompt_path.is_file(), prompt_path
