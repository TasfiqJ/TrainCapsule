from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .util import append_jsonl_locked, redact_sensitive


def append_provenance(path: Path, event: dict[str, Any]) -> None:
    """Write local automation provenance without changing public commit messages.

    The file lives under factory/state and is excluded from product commits. It preserves an
    honest audit trail while Git uses the repository owner's configured name and email.
    """

    payload = {
        "schema_version": 3,
        "recorded_at": datetime.now(UTC).isoformat(),
        "exportability_class": "INTERNAL_OPERATIONAL",
        "redacted": True,
        **json.loads(redact_sensitive(json.dumps(event, default=str))),
    }
    append_jsonl_locked(path, payload)
