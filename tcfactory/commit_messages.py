from __future__ import annotations

import re

from .models import CommitType, RoleName, TaskPacket

_MAX_SUBJECT = 72
_PREFIX_RE = re.compile(r"^(?:\[[^\]]+\]\s*)+")
_NON_WORD_RE = re.compile(r"[^a-z0-9._/-]+")


def _clean_subject(value: str) -> str:
    text = _PREFIX_RE.sub("", value.strip()).lower()
    text = re.sub(r"\btraincapsule\b", "", text)
    text = re.sub(r"\bimplement\b", "add", text)
    text = re.sub(r"\bcreate\b", "add", text)
    text = re.sub(r"\bwrite\b", "add", text)
    text = re.sub(r"\bcomplete\b", "finish", text)
    text = _NON_WORD_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" ._-/")
    return text or "update project"


def format_commit_message(
    kind: CommitType | str, subject: str, *, limit: int = _MAX_SUBJECT
) -> str:
    prefix = f"{CommitType(kind).value}: "
    cleaned = _clean_subject(subject)
    available = max(8, limit - len(prefix))
    if len(cleaned) > available:
        cleaned = cleaned[:available].rstrip(" ._-/")
    return prefix + cleaned


def stage_commit_message(task: TaskPacket, role: RoleName, *, checkpoint: bool = False) -> str:
    subject = task.commit_subject or task.title
    if checkpoint:
        subject = f"save {task.task_id.lower()} progress"
        kind = CommitType.CHORE
    elif role in {RoleName.PLANNER, RoleName.SPECIFICATION, RoleName.RESEARCH}:
        kind = CommitType.SPEC if task.commit_type == CommitType.FEAT else task.commit_type
    else:
        kind = task.commit_type
    return format_commit_message(kind, subject)


def controller_commit_message(action: str, target: str | None = None) -> str:
    """Return a short plain-English controller commit subject.

    Final repository history uses the operator's configured Git identity and simple subjects.
    Detailed AI provenance lives in the local provenance ledger rather than noisy commit text.
    """

    subject = _clean_subject(f"{action} {target or ''}".strip())
    return subject[:50].rstrip(" ._-/") or "update project"
