from __future__ import annotations

import re
from pathlib import Path

from tcfactory.github_sync import load_github_config

EXPECTED_FILES = {
    "factory-quality.yml": "TrainCapsule / Factory quality",
    "product-unit.yml": "TrainCapsule / Product unit",
    "product-contract.yml": "TrainCapsule / Product contract",
    "security.yml": "TrainCapsule / Security",
    "source-of-truth-integrity.yml": "TrainCapsule / Source-of-truth integrity",
}


def test_required_workflow_files_and_config_names_match() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow_root = root / ".github" / "workflows"
    config = load_github_config(root / "config" / "github.yaml")
    observed_files = {path.name for path in workflow_root.glob("*.yml")}

    assert observed_files == set(EXPECTED_FILES)
    assert config.remote_ci.required_workflows == list(EXPECTED_FILES.values())
    assert config.release_mode == "pull_request"
    assert config.direct_main_push is False


def test_required_workflows_are_bounded_hosted_and_secret_free() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow_root = root / ".github" / "workflows"
    action = re.compile(r"uses:\s+[^\s@]+@([0-9a-f]{40})(?:\s|$)")

    for filename, name in EXPECTED_FILES.items():
        text = (workflow_root / filename).read_text(encoding="utf-8")
        assert f"name: {name}" in text
        assert "runs-on: ubuntu-latest" in text
        assert "timeout-minutes:" in text
        assert "concurrency:" in text
        assert "permissions:\n  contents: read" in text
        assert "retention-days:" in text
        assert "pull_request:" in text
        assert "${{ secrets" not in text
        uses = [line for line in text.splitlines() if "uses:" in line]
        assert uses
        assert all(action.search(line) for line in uses)


def test_workflow_test_scopes_are_explicit() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow_root = root / ".github" / "workflows"
    assert "tests --ignore=tests/product" in (
        workflow_root / "factory-quality.yml"
    ).read_text(encoding="utf-8")
    product_unit = (workflow_root / "product-unit.yml").read_text(encoding="utf-8")
    product_contract = (workflow_root / "product-contract.yml").read_text(
        encoding="utf-8"
    )
    assert "generate_product_schemas.py --check" in product_unit
    assert "tests/product/test_identity.py" in product_unit
    assert "tests/product/test_evidence_store.py" in product_unit
    assert "tests/product/test_flight_recorder_importer.py" in product_contract
    assert "tests/product/test_cli.py" in product_contract
