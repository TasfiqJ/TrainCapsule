"""Emit the exact receipt-bound evidence roster consumed by the root observer."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from tcfactory.gitops import current_sha
from tcfactory.util import atomic_write_bytes, sha256_file

from .base import sha256_digest
from .canaries import PostActivationObservationId
from .contracts_v31 import ActivationReceiptV31
from .runtime_paths import V3RuntimePaths

ACTIVATION_RECEIPT = Path("/var/lib/traincapsule-verifier/activation/current.json")


def _canonical(payload: Mapping[str, object]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def emit_post_activation_events(
    *,
    repo_root: Path,
    paths: V3RuntimePaths,
    cycle_result: dict[str, object],
    activation_receipt_path: Path = ACTIVATION_RECEIPT,
    invocation_id: str | None = None,
    stdin_is_tty: bool | None = None,
    now: datetime | None = None,
) -> bool:
    """Emit the seven events once their live facts are all simultaneously true."""

    if cycle_result.get("status") != "IDLE" or paths.stop.exists():
        return False
    blockers = cycle_result.get("scopedBlockers")
    if not isinstance(blockers, dict):
        return False
    blockers = cast(dict[str, object], blockers)
    external = blockers.get("externalEvidence")
    if not isinstance(external, list) or not external:
        return False
    external = cast(list[object], external)
    state_payload: object = json.loads(paths.controller_state.read_bytes())
    if not isinstance(state_payload, dict):
        return False
    state_payload = cast(dict[str, object], state_payload)
    cycles = state_payload.get("cycles")
    if not isinstance(cycles, int) or cycles < 2:
        return False
    decisions = sorted(paths.scheduler_decisions.glob("cycle-*.json"))
    if not decisions:
        return False
    invocation_id = invocation_id or os.environ.get("INVOCATION_ID")
    stdin_is_tty = sys.stdin.isatty() if stdin_is_tty is None else stdin_is_tty
    if not invocation_id or stdin_is_tty:
        return False

    receipt = ActivationReceiptV31.model_validate_json(
        activation_receipt_path.read_bytes(), strict=True
    )
    main_sha = current_sha(repo_root, "HEAD")
    tree_sha = current_sha(repo_root, "HEAD^{tree}")
    if receipt.mode.value != "LIVE" or receipt.verified_main_sha != main_sha:
        return False
    receipt_digest = receipt.canonical_digest()
    evidence_root = paths.state_root / "post-activation-events" / receipt.receipt_id
    marker = evidence_root / "EMITTED"
    if marker.is_file():
        return False

    latest_decision = decisions[-1].resolve(strict=True)
    roster: list[tuple[PostActivationObservationId, dict[str, object]]] = [
        (
            PostActivationObservationId.COMPLETE_AUTONOMOUS_CYCLE,
            {"controllerCycles": cycles, "cycleStatus": "IDLE"},
        ),
        (
            PostActivationObservationId.IDLE_CYCLE,
            {"cycleResult": cycle_result},
        ),
        (
            PostActivationObservationId.EXTERNAL_WAIT_ISOLATED_CYCLE,
            {"externalEvidenceWorkItems": external, "controllerContinued": True},
        ),
        (
            PostActivationObservationId.SERVICE_RESTART,
            {"invocationId": invocation_id, "processId": os.getpid()},
        ),
        (
            PostActivationObservationId.NEXT_WORK_SCHEDULING,
            {
                "schedulerDecision": str(latest_decision),
                "schedulerDecisionDigest": sha256_file(latest_decision),
            },
        ),
        (
            PostActivationObservationId.NO_DIRECT_MAIN_PUSH,
            {"verifiedMainSha": main_sha, "verifiedMainTreeSha": tree_sha},
        ),
        (
            PostActivationObservationId.NO_HUMAN_CLICK,
            {"serviceInvocation": True, "stdinIsTty": False},
        ),
    ]
    evidence_root.mkdir(parents=True, exist_ok=True)
    occurred_at = (now or datetime.now(UTC)).astimezone(UTC)
    messages: list[str] = []
    for sequence, (event_id, evidence) in enumerate(roster, start=1):
        artifact = evidence_root / f"{event_id.value}.json"
        raw = _canonical(
            {
                "schemaVersion": "3.1",
                "observationId": event_id.value,
                "activationReceiptId": receipt.receipt_id,
                "activationReceiptDigest": receipt_digest,
                "exactMainSha": main_sha,
                "exactTreeSha": tree_sha,
                "evidence": evidence,
            }
        )
        atomic_write_bytes(artifact, raw)
        event: dict[str, object] = {
            "schemaVersion": "3.1",
            "eventId": event_id.value,
            "activationReceiptId": receipt.receipt_id,
            "activationReceiptDigest": receipt_digest,
            "exactMainSha": main_sha,
            "exactTreeSha": tree_sha,
            "sequence": sequence,
            "occurredAt": (occurred_at + timedelta(microseconds=sequence)).isoformat(),
            "artifactPath": str(artifact.resolve(strict=True)),
            "artifactDigest": sha256_digest(raw),
        }
        messages.append("TCF_V31_EVENT " + _canonical(event).decode("utf-8").strip())
    for message in messages:
        print(message, flush=True)
    atomic_write_bytes(marker, b"emitted\n")
    return True
