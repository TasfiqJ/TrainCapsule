from __future__ import annotations

from pathlib import Path

import pytest
from traincapsule_verifier import canary_receipt_probe


def test_ephemeral_receipt_probe_executes_all_four_real_negative_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The probe creates a new in-memory authority; no production key or receipt is reachable.
    monkeypatch.setattr(
        "sys.argv",
        ["traincapsule-verifier-canary-receipt-probe", "--artifact-root", str(tmp_path)],
    )
    assert canary_receipt_probe.main() == 0


def test_probe_source_contains_no_production_authority_path() -> None:
    source = Path(canary_receipt_probe.__file__).read_text()
    assert "/var/lib/traincapsule-verifier/private" not in source
    assert "load_pem_private_key" not in source
    assert "Ed25519PrivateKey.generate()" in source
