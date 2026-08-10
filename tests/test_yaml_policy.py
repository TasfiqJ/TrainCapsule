from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from tcfactory.yamlutil import DuplicateYamlKeyError, load_yaml_text


def test_duplicate_yaml_keys_fail_closed() -> None:
    with pytest.raises(DuplicateYamlKeyError, match="Duplicate YAML key"):
        load_yaml_text("enabled: true\nenabled: false\n", source="test.yaml")


def test_repository_yaml_has_unique_keys() -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "verify_yaml_unique.py"
    namespace = {"__name__": "not_main", "__file__": str(script)}
    exec(compile(script.read_text(encoding="utf-8"), str(script), "exec"), namespace)
    main = cast(Callable[[], int], namespace["main"])
    assert main() == 0
