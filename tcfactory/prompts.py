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
    encoded_manifest = json.dumps(context_manifest, indent=2, sort_keys=True)
    max_chars = stage.max_context_chars or 100_000
    if len(encoded_manifest) > max_chars:
        raise ValueError("context manifest exceeds the active stage context-size budget")
    lowered = encoded_manifest.lower()
    if "advisory_career" in lowered or "advisory_acquisition" in lowered:
        raise ValueError("routine task prompt contains excluded career/acquisition context")
    packet = task.model_dump(mode="json")
    packet["active_stage"] = stage.model_dump(mode="json")
    packet["attempt"] = attempt
    return f"""Complete the active TrainCapsule stage to its objective exit contract.

TASK PACKET (authoritative for this run):
```json
{json.dumps(packet, indent=2, sort_keys=True)}
```

CONTEXT MANIFEST (candidate-bound routing and evidence, not conversational history):
```json
{encoded_manifest}
```

Operational rules:
1. Treat the manifest as the complete authorized context routing set for this stage. Retrieve
   details just in time from only the named sources; do not load company, buyer, acquisition,
   career, commercial, or release context unless the manifest explicitly includes it.
2. Inspect the current candidate and exact diff before changing anything.
3. Stay within active_stage.allowed_paths and avoid every forbidden path.
4. Run cheap deterministic gates early, then perform every broader investigation, real-boundary
   exercise, and objective-stage check required for a production outcome.
5. Resolve every concrete previous finding without weakening tests, contracts, fixtures,
   or status semantics.
6. Do not ask for interactive clarification. When authority is genuinely missing or
   contradictory, return verdict `blocked` and identify the exact missing authority.
7. Work only within this finite session and its declared ceilings. If bounded attempts are
   exhausted, preserve the candidate and return the exact lawful state: `DEFER`,
   `NATIVE_SUFFICIENT`, `REJECTED_VALUE`, `WAITING_EXTERNAL`, or `WAITING_HUMAN`.
8. End each session with one structured AgentReport matching the enforced JSON schema. Machine
   evidence, not confidence, determines promotion.
"""
