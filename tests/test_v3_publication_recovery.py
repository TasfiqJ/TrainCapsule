from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from tcfactory.github_sync import GitHubConfig, MainOnlyPublisher


def test_legacy_main_publisher_is_unreachable_under_v31(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="legacy V3 publication adapter is disabled"):
        MainOnlyPublisher(
            repo_root=tmp_path,
            config=GitHubConfig(),
            receipt_root=tmp_path / "receipts",
            quarantine_root=tmp_path / "quarantine",
            local_gate_command=("true",),
        )


@pytest.mark.parametrize(
    "override",
    [
        {"directMainPush": True},
        {"releaseMode": "owner_directed_main_only"},
        {"publisherCapability": "READY"},
        {"visibility": "private"},
    ],
)
def test_v31_github_config_rejects_direct_main_or_unproven_capability(
    override: dict[str, object],
) -> None:
    payload = GitHubConfig().model_dump(mode="json", by_alias=True)
    payload.update(override)
    with pytest.raises(ValidationError):
        GitHubConfig.model_validate(payload)
