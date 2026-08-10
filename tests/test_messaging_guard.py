import json
import os
import subprocess
from pathlib import Path

HOOK = Path(".claude/hooks/messaging_guard.py").resolve()
ALLOWED_PEER = "rp-demo-001-integration-scout-t060925z-a2"


def run_hook(tmp_path: Path, recipient: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(
        {
            "TCF_PEER_MESSAGING": "1",
            "TCF_ALLOWED_PEERS_JSON": json.dumps([ALLOWED_PEER]),
            "TCF_MAX_MESSAGE_CHARS": "1200",
            "TCF_MAX_MESSAGES": "4",
            "TCF_MESSAGE_AUDIT_PATH": str(tmp_path / "peer-messages.jsonl"),
            "TCF_TASK_ID": "DEMO-001",
            "TCF_ACTIVE_ROLE": "builder",
            "TCF_SESSION_NAME": "rp-demo-001-builder-t060925z-a2",
        }
    )
    payload = {
        "tool_name": "SendMessage",
        "tool_input": {
            "recipient": recipient,
            "message": "RPMSG/1 task=DEMO-001 sha=none artifact=peer://calibration",
        },
    }
    return subprocess.run(
        ["python3", str(HOOK)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )


def test_discovered_reference_for_allowed_peer_is_accepted(tmp_path: Path) -> None:
    result = run_hook(tmp_path, f"{ALLOWED_PEER} [df4752]")

    assert result.returncode == 0
    assert result.stdout == ""
    record = json.loads((tmp_path / "peer-messages.jsonl").read_text(encoding="utf-8"))
    assert record["recipient"] == f"{ALLOWED_PEER} [df4752]"


def test_reference_cannot_bypass_peer_name_allowlist(tmp_path: Path) -> None:
    result = run_hook(tmp_path, "rp-demo-001-untrusted-t060925z-a2 [df4752]")

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_malformed_reference_is_denied(tmp_path: Path) -> None:
    result = run_hook(tmp_path, f"{ALLOWED_PEER} [not-a-ref]")

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
