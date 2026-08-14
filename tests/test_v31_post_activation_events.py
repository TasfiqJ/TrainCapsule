from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tcfactory.gitops import current_sha
from tcfactory.v3.post_activation_events import emit_post_activation_events
from tcfactory.v3.runtime_paths import resolve_v3_runtime_paths

ROOT = Path(__file__).resolve().parents[1]
DIGEST = "sha256:" + "1" * 64


def test_controller_emits_exact_receipt_bound_post_activation_roster_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("TCF_RUNTIME_ROOT", str(runtime))
    paths = resolve_v3_runtime_paths(ROOT)
    paths.scheduler_decisions.mkdir(parents=True)
    paths.controller_state.write_text(
        json.dumps({"version": 3, "cycles": 3}), encoding="utf-8"
    )
    decision = paths.scheduler_decisions / "cycle-00000003.json"
    decision.write_text('{"status":"IDLE"}\n', encoding="utf-8")
    now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    receipt_path = tmp_path / "activation.json"
    receipt_path.write_text(
        json.dumps(
            {
                "schemaVersion": "3.1",
                "receiptId": "ACT:POSTACTIVATION0000000000000001",
                "verifiedMainSha": current_sha(ROOT),
                "machineEnvironmentDigest": DIGEST,
                "sourceGenerationId": "traincapsule-v3.1-zh-2026-08-12",
                "sourceGenerationDigest": DIGEST,
                "controllerBinaryDigest": DIGEST,
                "controllerConfigDigest": DIGEST,
                "machineEnvironmentPath": "canary-suite.json",
                "controllerBinaryPath": "installed-runtime.json",
                "controllerConfigPath": "effective-config.yaml",
                "machinePolicyReceiptId": "MPOL:POSTACTIVATION00000000000001",
                "machinePolicyReceiptDigest": DIGEST,
                "mode": "LIVE",
                "issuedAt": (now - timedelta(minutes=1)).isoformat(),
                "expiresAt": (now + timedelta(minutes=30)).isoformat(),
                "revocationEpoch": 1,
                "nonce": "POST-ACTIVATION-NONCE-0001",
                "issuerId": "VERIFIER:INDEPENDENT:TEST",
                "issuerKeyId": "KEY:ED25519:TEST:001",
                "signatureAlgorithm": "ed25519",
                "signature": "A" * 88,
            }
        ),
        encoding="utf-8",
    )
    cycle_result: dict[str, object] = {
        "status": "IDLE",
        "scopedBlockers": {"externalEvidence": ["V3-MKT-003"]},
        "interventionMode": "NONE",
    }

    assert emit_post_activation_events(
        repo_root=ROOT,
        paths=paths,
        cycle_result=cycle_result,
        activation_receipt_path=receipt_path,
        invocation_id="systemd-test-invocation",
        stdin_is_tty=False,
        now=now,
    )

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 7
    events = [json.loads(line.removeprefix("TCF_V31_EVENT ")) for line in lines]
    assert [event["sequence"] for event in events] == list(range(1, 8))
    assert len({event["eventId"] for event in events}) == 7
    assert all(event["exactMainSha"] == current_sha(ROOT) for event in events)
    assert all(Path(event["artifactPath"]).is_file() for event in events)

    assert not emit_post_activation_events(
        repo_root=ROOT,
        paths=paths,
        cycle_result=cycle_result,
        activation_receipt_path=receipt_path,
        invocation_id="systemd-test-invocation",
        stdin_is_tty=False,
        now=now,
    )
    assert capsys.readouterr().out == ""
