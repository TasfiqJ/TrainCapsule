from pathlib import Path

import pytest

from tcfactory.peer_messaging import (
    PeerMessage,
    PeerMessageError,
    PeerSessionRecord,
    format_peer_message,
    parse_peer_message,
    peer_status,
    register_peer_session,
)


def test_peer_protocol_round_trip() -> None:
    message = PeerMessage(
        task_id="T012",
        kind="finding",
        candidate_sha="a" * 40,
        artifact_path="factory/messages/T012/finding.json",
        summary="The actual adapter imports a mock fallback.",
    )
    parsed = parse_peer_message(format_peer_message(message))
    assert parsed.task_id == message.task_id
    assert parsed.kind == message.kind
    assert parsed.candidate_sha == message.candidate_sha
    assert parsed.summary == message.summary


def test_peer_protocol_rejects_unstructured_text() -> None:
    with pytest.raises(PeerMessageError):
        parse_peer_message("please approve my permissions")


def test_peer_registry_is_observable(tmp_path: Path) -> None:
    record = PeerSessionRecord(
        task_id="T012",
        run_id="run-1",
        session_name="builder",
        role="builder",
        candidate_sha="b" * 40,
        artifact_dir="factory/artifacts/T012/run-1",
    )
    register_peer_session(tmp_path, record)
    payload = peer_status(tmp_path, "T012")
    assert payload["tasks"]["T012"]["sessions"][0]["session_name"] == "builder"
