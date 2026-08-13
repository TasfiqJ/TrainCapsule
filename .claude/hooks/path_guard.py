#!/usr/bin/env python3
from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import NoReturn, cast
from urllib.parse import urlparse


def deny(reason: str) -> NoReturn:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    raise SystemExit(0)


def object_dict(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        deny(f"{label} must be an object")
    return cast(dict[str, object], value)


def string_list_env(name: str) -> list[str]:
    value: object = json.loads(os.environ.get(name, "[]"))
    if not isinstance(value, list):
        deny(f"{name} must contain a JSON string array")
    items = cast(list[object], value)
    if not all(isinstance(item, str) for item in items):
        deny(f"{name} must contain a JSON string array")
    return cast(list[str], items)


def bash_rules_env() -> list[tuple[str, list[str]]]:
    value: object = json.loads(os.environ.get("TCF_BASH_RULES_JSON", "[]"))
    if not isinstance(value, list):
        deny("TCF_BASH_RULES_JSON must contain a JSON array")
    rules: list[tuple[str, list[str]]] = []
    for raw_rule in cast(list[object], value):
        rule = object_dict(raw_rule, "Bash rule")
        executable = rule.get("executable")
        prefix = rule.get("argumentPrefix")
        if not isinstance(executable, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}", executable
        ):
            deny("Bash rule executable is invalid")
        if not isinstance(prefix, list):
            deny("Bash rule argumentPrefix must be a string array")
        prefix_objects = cast(list[object], prefix)
        if not all(isinstance(argument, str) for argument in prefix_objects):
            deny("Bash rule argumentPrefix must be a string array")
        rules.append((executable, cast(list[str], prefix_objects)))
    return rules


def matches(path: str, patterns: list[str]) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    return any(fnmatch.fnmatch(normalized, pattern.lstrip("./")) for pattern in patterns)


def host_allowed(host: str, allowed_domains: list[str]) -> bool:
    normalized = host.lower().rstrip(".")
    return any(
        normalized == domain.lower().rstrip(".")
        or normalized.endswith("." + domain.lower().rstrip("."))
        for domain in allowed_domains
    )


def resolve_inside_root(root: Path, raw_value: object, *, label: str) -> tuple[Path, str]:
    if not isinstance(raw_value, str) or not raw_value.strip():
        deny(f"{label} lacks a usable path")
    raw = Path(raw_value)
    path = (root / raw).resolve() if not raw.is_absolute() else raw.resolve()
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        deny(f"{label} path escapes the task worktree: {path}")
    return path, rel


def main() -> None:
    payload = object_dict(json.load(sys.stdin), "Hook payload")
    tool = str(payload.get("tool_name", ""))
    tool_input = object_dict(payload.get("tool_input") or {}, "Tool input")
    root = Path(os.environ.get("TCF_REPO_ROOT", os.getcwd())).resolve()
    allowed = string_list_env("TCF_ALLOWED_PATHS_JSON")
    forbidden = string_list_env("TCF_FORBIDDEN_PATHS_JSON")
    allowed_domains = string_list_env("TCF_ALLOWED_DOMAINS_JSON")
    read_only = os.environ.get("TCF_READ_ONLY") == "1"

    if tool == "Read":
        resolve_inside_root(root, tool_input.get("file_path"), label="Read")
        return

    if tool in {"Grep", "Glob"}:
        raw_path = tool_input.get("path")
        if raw_path is not None:
            resolve_inside_root(root, raw_path, label=tool)
        return

    if tool in {"Write", "Edit"}:
        if read_only:
            deny(f"Role is read-only; {tool} is prohibited")
        _, rel = resolve_inside_root(root, tool_input.get("file_path"), label=tool)
        if forbidden and matches(rel, forbidden):
            deny(f"Protected path is forbidden for this task: {rel}")
        if allowed and not matches(rel, allowed):
            deny(f"Path is outside this task's allowlist: {rel}")
        return

    if tool == "WebFetch":
        if not allowed_domains:
            deny("WebFetch is disabled for this task")
        raw_url = tool_input.get("url")
        if not isinstance(raw_url, str):
            deny("WebFetch call lacks a URL")
        parsed = urlparse(raw_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            deny(f"WebFetch URL is invalid or unsupported: {raw_url}")
        if not host_allowed(parsed.hostname, allowed_domains):
            deny(
                f"WebFetch domain {parsed.hostname!r} is outside the task allowlist: "
                + ", ".join(allowed_domains)
            )
        return

    if tool == "WebSearch":
        if not allowed_domains:
            deny("WebSearch is disabled for this task")
        query = str(tool_input.get("query", ""))
        site_filters = [f"site:{domain.lower()}" for domain in allowed_domains]
        if not any(site in query.lower() for site in site_filters):
            deny(
                "WebSearch must be restricted with a site: filter for at least one allowed "
                f"domain: {', '.join(allowed_domains)}"
            )
        return

    if tool == "Bash":
        command = str(tool_input.get("command", ""))
        if re.search(r"(?:&&|\|\||[;|<>`\n]|\$\(|\$\{)", command):
            deny("Bash command contains shell composition or expansion")
        try:
            arguments = shlex.split(command, posix=True)
        except ValueError:
            deny("Bash command is not valid shell token syntax")
        rules = bash_rules_env()
        if not arguments or not any(
            arguments[0] == executable
            and arguments[1 : 1 + len(prefix)] == prefix
            for executable, prefix in rules
        ):
            deny("Bash executable or argument prefix is outside the task allowlist")
        blocked = [
            r"(^|[;&|]\s*)sudo\b",
            r"\bgit\s+(push|reset\s+--hard|clean|checkout|switch|rebase|worktree|commit|add|merge|cherry-pick|tag)\b",
            r"\b(chmod|chown)\b",
            r"\b(docker|podman)\b",
            r"\b(powershell(?:\.exe)?|pwsh(?:\.exe)?|cmd\.exe|wsl\.exe)\b",
            r"\brm\s+-[^\n]*r[^\n]*f\b",
            r"/var/run/docker\.sock",
            r"dangerouslyDisableSandbox",
            r"(?:~|\$HOME)/\.config/traincapsule",
            r"(?:~|\$HOME)/\.local/share/traincapsule-factory/private-gates",
            r"(?:~|\$HOME)/\.claude/\.credentials\.json",
            r"(?:~|\$HOME)/\.config/gh",
            r"(?:~|\$HOME)/\.git-credentials",
            r"(?:~|\$HOME)/\.ssh",
            r"(?:~|\$HOME)/\.netrc",
            r"(?:~|\$HOME)/\.(?:aws|azure|kube|docker)",
            r"(?:~|\$HOME)/\.config/gcloud",
            r"\bgh\s+(?:auth|repo\s+create|secret|variable)\b",
            r"/proc/(?:self|thread-self|\d+)/environ",
            r"CLAUDE_CODE_OAUTH_TOKEN",
            r"TCF_CLAUDE_OAUTH_TOKEN_FILE",
            r"TCF_PRIVATE_GATE_RUNNER",
        ]
        for pattern in blocked:
            if re.search(pattern, command, flags=re.IGNORECASE):
                deny(f"Bash command blocked by TrainCapsule factory policy: {pattern}")
        if read_only and re.search(
            r"(^|[;&|]\s*)(cat\s+.*>|tee\b|sed\s+-i\b|perl\s+-pi\b|"
            r"python[^\n]*write_text|python[^\n]*open\([^\n]*['\"]w)",
            command,
        ):
            deny("Read-only role attempted a likely file-modifying shell command")


if __name__ == "__main__":
    main()
