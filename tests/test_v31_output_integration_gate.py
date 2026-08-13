from __future__ import annotations

import sys
from collections.abc import Callable
from importlib import util
from pathlib import Path
from typing import cast


def _violations_function() -> Callable[[Path], list[str]]:
    gates = Path(__file__).resolve().parents[1] / "scripts/gates"
    sys.path.insert(0, str(gates))
    try:
        spec = util.spec_from_file_location(
            "v31_output_and_integration_gate", gates / "output_and_integration_gate.py"
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("output/integration gate import spec is unavailable")
        module = util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return cast(Callable[[Path], list[str]], module._v31_repository_violations)
    finally:
        sys.path.remove(str(gates))


def _fixture(root: Path) -> None:
    sources = {
        "tcfactory/v3/controller.py": "\n".join(
            (
                "import tcfactory.v3.task_compiler_v31",
                "import tcfactory.v3.external_actions",
                "import tcfactory.v3.native_value_runtime",
            )
        ),
        "tcfactory/cli.py": "from .v3.activation import activate\nfrom .v3.canaries import run\n",
        "verifier/src/traincapsule_verifier/bootstrap.py": (
            "# traincapsule-verifier-request-broker\n"
            "# traincapsule-verifier-issuer\n"
            "# traincapsule-verifier-broker\n"
        ),
        "verifier/src/traincapsule_verifier/issuer_service.py": "verifier.issue_receipt()\n",
    }
    for relative, source in sources.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")


def test_v31_repository_gate_rejects_production_placeholder_and_dead_sidecar(
    tmp_path: Path,
) -> None:
    violations_for = _violations_function()
    _fixture(tmp_path)
    assert violations_for(tmp_path) == []
    controller = tmp_path / "tcfactory/v3/controller.py"
    controller.write_text("def run():\n    raise NotImplementedError\n", encoding="utf-8")
    violations = violations_for(tmp_path)
    assert any("NotImplementedError" in item for item in violations)
    assert any("dead-sidecar:tcfactory.v3.task_compiler_v31" in item for item in violations)
