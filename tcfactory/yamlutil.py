from __future__ import annotations

from pathlib import Path
from typing import Any, TextIO, cast

import yaml


class DuplicateYamlKeyError(ValueError):
    """Raised when a YAML mapping repeats a key.

    PyYAML normally accepts the last value silently. Configuration, task, and roadmap
    files are authority-bearing inputs, so duplicate keys must fail closed instead.
    """


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key: Any = cast(Any, loader).construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise DuplicateYamlKeyError(
                f"Unhashable YAML mapping key at line {key_node.start_mark.line + 1}"
            ) from exc
        if duplicate:
            source = getattr(loader, "_source_name", "<yaml>")
            raise DuplicateYamlKeyError(
                f"Duplicate YAML key {key!r} in {source} at line {key_node.start_mark.line + 1}"
            )
        mapping[key] = cast(Any, loader).construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_yaml_text(text: str, *, source: str = "<yaml>") -> Any:
    loader = _UniqueKeyLoader(text)
    loader._source_name = source  # type: ignore[attr-defined]
    try:
        return loader.get_single_data()
    finally:
        cast(Any, loader).dispose()


def load_yaml(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"YAML file not found: {path}")
    return load_yaml_text(path.read_text(encoding="utf-8"), source=str(path))


def load_yaml_file(handle: TextIO) -> Any:
    source = getattr(handle, "name", "<yaml>")
    return load_yaml_text(handle.read(), source=str(source))
