from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def append_provenance(path: Path, event: dict[str, Any]) -> None:
    """Write local automation provenance without changing public commit messages.

    The file lives under factory/state and is excluded from product commits. It preserves an
    honest audit trail while Git uses the repository owner's configured name and email.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"recorded_at": datetime.now(UTC).isoformat(), **event}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
