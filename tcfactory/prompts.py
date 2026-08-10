from __future__ import annotations

import json
from pathlib import Path

from .models import RoleConfig, Stage, TaskPacket


def load_prompt(repo_root: Path, path: str) -> str:
    prompt_path = Path(path)
    if not prompt_path.is_absolute():
        prompt_path = repo_root / prompt_path
    return prompt_path.read_text(encoding="utf-8")


def compose_system_prompt(
    *, repo_root: Path, global_prompt_path: str, role: RoleConfig, role_name: str
) -> str:
    global_prompt = load_prompt(repo_root, global_prompt_path)
    role_prompt = load_prompt(repo_root, role.prompt_file)
    return (
        f"{global_prompt}\n\n"
        f"# Active role: {role_name}\n\n"
        f"{role_prompt}\n\n"
        "The task packet, accepted ADRs, protected assets, and deterministic machine gates "
        "outrank your preferences. Do not self-authorize changes outside the task."
    )


def compose_task_prompt(
    task: TaskPacket,
    stage: Stage,
    *,
    attempt: int,
    context_manifest: dict[str, object],
) -> str:
    packet = task.model_dump(mode="json")
    packet["active_stage"] = stage.model_dump(mode="json")
    packet["attempt"] = attempt
    return f"""Execute exactly one bounded TrainCapsule work unit.

TASK PACKET (authoritative for this run):
```json
{json.dumps(packet, indent=2, sort_keys=True)}
```

BOUNDED CONTEXT MANIFEST (paths and evidence, not conversational history):
```json
{json.dumps(context_manifest, indent=2, sort_keys=True)}
```

Operational rules:
1. Read only the named sources and relevant code paths just in time. Do not load the entire
   repository, master plan, or prior transcripts.
2. Inspect the current candidate and exact diff before changing anything.
3. Stay within active_stage.allowed_paths and avoid every forbidden path.
4. Run cheap deterministic gates before spending time on broad review or speculation.
5. Resolve every concrete previous finding without weakening tests, contracts, fixtures,
   or status semantics.
6. Do not ask for interactive clarification. When authority is genuinely missing or
   contradictory, return verdict `blocked` and identify the exact missing authority.
7. End with one structured AgentReport matching the enforced JSON schema. Machine evidence,
   not confidence, determines promotion.
"""
