"""Immutable, non-authoritative local pilot metadata.

Pilot records are content-addressed local planning artifacts.  They can never
act as customer evidence, a commercial decision, or a release approval.
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from tcfactory.util import read_json
from tcfactory.v3.base import V3Model


class PilotMetadata(V3Model):
    version: Literal[3] = 3
    pilot_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    status: Literal["LOCAL_DRAFT"] = "LOCAL_DRAFT"
    evidence_authority: Literal["NONE"] = "NONE"
    commercial_maturity: Literal["UNKNOWN"] = "UNKNOWN"
    decision_authority: Literal["NONE"] = "NONE"
    external_evidence_refs: list[str] = Field(default_factory=list, max_length=0)
    automatic_promotion: Literal[False] = False
    owner_directives_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    created_at: datetime


def _owner_directives_digest(repo_root: Path) -> str:
    content = (repo_root / "config/owner_directives.yaml").read_bytes()
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def pilot_root(repo_root: Path) -> Path:
    return repo_root.resolve() / "factory/state/pilots"


def create_pilot_metadata(
    repo_root: Path,
    pilot_id: str,
    *,
    created_at: datetime | None = None,
) -> Path:
    record = PilotMetadata(
        pilot_id=pilot_id,
        owner_directives_digest=_owner_directives_digest(repo_root),
        created_at=created_at or datetime.now(UTC),
    )
    directory = pilot_root(repo_root) / record.pilot_id
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.glob("*.json")):
        raise ValueError("pilot metadata already exists and is immutable")
    digest = record.canonical_digest().removeprefix("sha256:")
    path = directory / f"{digest}.json"
    try:
        with path.open("xb") as stream:
            stream.write(record.canonical_json_bytes())
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise ValueError("pilot metadata already exists and is immutable") from exc
    path.chmod(0o444)
    return path


def load_pilot_metadata(repo_root: Path, pilot_id: str) -> tuple[Path, PilotMetadata]:
    # Model validation is also the path-traversal boundary for pilot_id.
    probe = PilotMetadata(
        pilot_id=pilot_id,
        owner_directives_digest=_owner_directives_digest(repo_root),
        created_at=datetime.now(UTC),
    )
    directory = pilot_root(repo_root) / probe.pilot_id
    paths = sorted(directory.glob("*.json")) if directory.is_dir() else []
    if len(paths) != 1:
        raise ValueError("pilot metadata is missing or ambiguous")
    path = paths[0]
    record = PilotMetadata.model_validate(read_json(path, {}))
    expected_name = record.canonical_digest().removeprefix("sha256:") + ".json"
    if path.name != expected_name:
        raise ValueError("pilot metadata content-address does not match its payload")
    if record.owner_directives_digest != _owner_directives_digest(repo_root):
        raise ValueError("pilot metadata is stale for the active owner directives")
    return path, record


def list_pilot_metadata(repo_root: Path) -> list[tuple[Path, PilotMetadata]]:
    root = pilot_root(repo_root)
    if not root.is_dir():
        return []
    records: list[tuple[Path, PilotMetadata]] = []
    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        records.append(load_pilot_metadata(repo_root, directory.name))
    return records
