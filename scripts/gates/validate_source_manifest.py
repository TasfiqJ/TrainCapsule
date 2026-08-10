from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "docs/source-of-truth/final-2026-08-09"
LOCKED_MANIFEST = ROOT / ".factory/source-locks/FINAL_MANIFEST.json"
CANONICAL_MANIFEST_SHA256 = "51872ae1eacce06869a5924143b896364372b2b95997dcd3b4e3af080c9e6bdc"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def object_dict(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise SystemExit(f"{label} must be a JSON object")
    return cast(dict[str, object], value)


def main() -> int:
    source_dir = Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else SOURCE_DIR
    if len(sys.argv) > 2:
        raise SystemExit("usage: validate_source_manifest.py [SOURCE_DIRECTORY]")
    manifest = source_dir / "FINAL_MANIFEST.json"
    for path in (manifest, LOCKED_MANIFEST):
        if not path.is_file():
            raise SystemExit(f"required source manifest is missing: {path}")
        if sha256(path) != CANONICAL_MANIFEST_SHA256:
            raise SystemExit(f"source manifest digest mismatch: {path}")
    if manifest.read_bytes() != LOCKED_MANIFEST.read_bytes():
        raise SystemExit("source manifest and independent repository lock differ")

    try:
        payload: object = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"source manifest is unreadable: {exc}") from exc
    files = object_dict(object_dict(payload, "Source manifest").get("files"), "files")
    expected_names = set(files)
    actual_names = {path.name for path in source_dir.iterdir() if path.is_file()}
    if actual_names != expected_names | {"FINAL_MANIFEST.json"}:
        missing = sorted(expected_names - actual_names)
        extra = sorted(actual_names - expected_names - {"FINAL_MANIFEST.json"})
        raise SystemExit(f"source bundle membership mismatch: missing={missing}, extra={extra}")

    for name, raw_record in files.items():
        record = object_dict(raw_record, f"manifest record for {name}")
        path = source_dir / name
        expected_hash = record.get("sha256")
        expected_bytes = record.get("bytes")
        if not isinstance(expected_hash, str) or not isinstance(expected_bytes, int):
            raise SystemExit(f"manifest record lacks typed digest/size fields: {name}")
        if path.stat().st_size != expected_bytes:
            raise SystemExit(f"source file size mismatch: {name}")
        if sha256(path) != expected_hash.lower():
            raise SystemExit(f"source file digest mismatch: {name}")

    print(f"PASS: canonical TrainCapsule source manifest and {len(files)} files verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
