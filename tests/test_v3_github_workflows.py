from __future__ import annotations

import re
from pathlib import Path

from tcfactory.github_sync import MACHINE_POLICY_CHECK, load_github_config

EXPECTED_FILES = {
    "factory-quality.yml": "TrainCapsule / Factory quality",
    "product-unit.yml": "TrainCapsule / Product unit",
    "product-contract.yml": "TrainCapsule / Product contract",
    "security.yml": "TrainCapsule / Security",
    "source-of-truth-integrity.yml": "TrainCapsule / Source-of-truth integrity",
    "packaging-install.yml": "TrainCapsule / Packaging install",
    "docs-schemas.yml": "TrainCapsule / Docs and schemas",
    "source-freshness.yml": "TrainCapsule / Source freshness",
}
OPTIONAL_MANUAL_FILES = {"gpu-validation.yml": "TrainCapsule / GPU validation"}
MACHINE_POLICY_APP_ID = 4580794


def test_required_workflow_files_and_config_names_match() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow_root = root / ".github" / "workflows"
    config = load_github_config(root / "config" / "github.yaml")
    observed_files = {path.name for path in workflow_root.glob("*.yml")}

    assert observed_files == set(EXPECTED_FILES) | set(OPTIONAL_MANUAL_FILES)
    assert config.remote_ci.required_workflows == [
        *EXPECTED_FILES.values(),
        MACHINE_POLICY_CHECK,
    ]
    assert config.release_mode == "DIRECT_MAIN_EXACT_SHA_MACHINE_RECEIPT_POST_PUSH_VERIFY"
    assert config.direct_main_push is True
    assert config.publisher_capability == "DIRECT_MAIN_V31_READY"
    assert (
        config.remote_ci.trusted_check_app_ids[MACHINE_POLICY_CHECK]
        == MACHINE_POLICY_APP_ID
    )


def test_required_workflows_are_bounded_portable_and_secret_free() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow_root = root / ".github" / "workflows"
    action = re.compile(r"uses:\s+[^\s@]+@([0-9a-f]{40})(?:\s|$)")

    for filename, name in EXPECTED_FILES.items():
        text = (workflow_root / filename).read_text(encoding="utf-8")
        assert f"name: {name}" in text
        assert "vars.TRAINCAPSULE_CI_RUNNER" in text
        assert "'[\"ubuntu-latest\"]'" in text
        assert "timeout-minutes:" in text
        assert "concurrency:" in text
        assert "permissions:\n  contents: read" in text
        if "upload-artifact" in text:
            assert "retention-days:" in text
            assert "include-hidden-files: true" in text
        assert "push:\n    branches: [main]" in text
        assert "pull_request:\n    branches: [main]" in text
        assert "merge_group:" in text
        assert "${{ secrets" not in text
        uses = [line for line in text.splitlines() if "uses:" in line]
        assert uses
        assert all(action.search(line) for line in uses)
        assert "astral-sh/setup-uv@d0d8abe699bfb85fec6de9f7adb5ae17292296ff" not in text
        if "astral-sh/setup-uv@" in text:
            assert "astral-sh/setup-uv@d0cc045d04ccac9d8b7881df0226f9e82c39688e" in text

    gpu = (workflow_root / "gpu-validation.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in gpu
    assert "push:" not in gpu
    assert "pull_request:" not in gpu


def test_workflow_test_scopes_are_explicit() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow_root = root / ".github" / "workflows"
    assert "tests --ignore=tests/product" in (workflow_root / "factory-quality.yml").read_text(
        encoding="utf-8"
    )
    product_unit = (workflow_root / "product-unit.yml").read_text(encoding="utf-8")
    product_contract = (workflow_root / "product-contract.yml").read_text(encoding="utf-8")
    assert "generate_product_schemas.py --check" in product_unit
    assert "Install product workspace packages" in product_unit
    assert "-e packages/traincapsule-core" in product_unit
    assert "tests/product/test_identity.py" in product_unit
    assert "tests/product/test_evidence_store.py" in product_unit
    assert "tests/product/test_flight_recorder_importer.py" in product_contract
    assert "tests/product/test_cli.py" in product_contract
    assert "Install product workspace packages" in product_contract
    assert "-e packages/traincapsule-cli" in product_contract
    docs_schemas = (workflow_root / "docs-schemas.yml").read_text(encoding="utf-8")
    packaging = (workflow_root / "packaging-install.yml").read_text(encoding="utf-8")
    assert "fetch-depth: 0" in product_contract
    assert "fetch-depth: 0" in docs_schemas
    assert "Install product workspace packages" in docs_schemas
    assert "uv sync --extra dev --frozen" in packaging
