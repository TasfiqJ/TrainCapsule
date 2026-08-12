#!/usr/bin/env python3
"""Generate a deterministic CycloneDX inventory for the active Python environment."""

from __future__ import annotations

import argparse
import json
from importlib import metadata
from pathlib import Path
from typing import Literal, TypedDict


class SbomComponent(TypedDict):
    type: Literal["library"]
    name: str
    version: str
    purl: str


class SbomPrimaryComponent(TypedDict):
    type: Literal["application"]
    name: str


class SbomMetadata(TypedDict):
    component: SbomPrimaryComponent


class SbomDocument(TypedDict):
    bomFormat: Literal["CycloneDX"]
    specVersion: Literal["1.5"]
    version: int
    metadata: SbomMetadata
    components: list[SbomComponent]


def build_sbom() -> SbomDocument:
    components: list[SbomComponent] = []
    seen: set[tuple[str, str]] = set()
    for distribution in metadata.distributions():
        name = str(distribution.metadata.get("Name") or "").strip()
        version = str(distribution.version).strip()
        if not name or not version:
            continue
        key = (name.casefold(), version)
        if key in seen:
            continue
        seen.add(key)
        normalized = name.replace("_", "-").lower()
        components.append(
            {
                "type": "library",
                "name": name,
                "version": version,
                "purl": f"pkg:pypi/{normalized}@{version}",
            }
        )
    components.sort(key=lambda value: (value["name"].casefold(), value["version"]))
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {"component": {"type": "application", "name": "traincapsule"}},
        "components": components,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(build_sbom(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
