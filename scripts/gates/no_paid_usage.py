from __future__ import annotations

import os
from pathlib import Path
from typing import cast

import yaml

DISALLOWED_BILLING_ENV = {
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
}


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping")
    return cast(dict[str, object], value)


def verify_no_paid_usage(root: Path) -> list[str]:
    failures: list[str] = []
    factory = _mapping(
        yaml.safe_load((root / "config/factory.yaml").read_text(encoding="utf-8")),
        "config/factory.yaml",
    )
    autonomy = _mapping(
        yaml.safe_load((root / "config/autonomy.yaml").read_text(encoding="utf-8")),
        "config/autonomy.yaml",
    )
    auth_source = (root / "tcfactory/auth.py").read_text(encoding="utf-8")

    if factory.get("version") == 3 or factory.get("schemaVersion") == "3.1":
        executors = _mapping(
            yaml.safe_load((root / "config/executors.yaml").read_text(encoding="utf-8")),
            "config/executors.yaml",
        )
        backends = _mapping(executors.get("backends"), "config/executors.yaml backends")
        default_backend = executors.get("defaultBackend")
        default = (
            _mapping(backends.get(default_backend), "default executor backend")
            if isinstance(default_backend, str)
            else {}
        )
        if not default or default.get("authentication") != "subscription":
            failures.append("V3 default executor must use subscription authentication")
        for label, payload in (
            ("config/factory.yaml", factory),
            ("config/autonomy.yaml", autonomy),
            ("config/executors.yaml", executors),
        ):
            if payload.get("allowPaidUsage") is not False:
                failures.append(f"{label} must keep allowPaidUsage: false")
    else:
        if factory.get("auth_mode") != "max_oauth_only":
            failures.append("config/factory.yaml must use auth_mode: max_oauth_only")
        if factory.get("allow_paid_usage") is not False:
            failures.append("config/factory.yaml must keep allow_paid_usage: false")
        if autonomy.get("allow_paid_usage") is not False:
            failures.append("config/autonomy.yaml must keep allow_paid_usage: false")
    if "TCF_USAGE_CREDITS_DISABLED_ACK" not in auth_source:
        failures.append("the usage-credits-disabled acknowledgement check was removed")
    for name in sorted(DISALLOWED_BILLING_ENV):
        if f'"{name}"' not in auth_source:
            failures.append(f"subscription routing guard is missing {name}")
        if os.getenv(name):
            failures.append(f"paid or alternate billing environment is active: {name}")
    if os.getenv("TCF_LIGHTS_OUT") == "1" and os.getenv(
        "TCF_USAGE_CREDITS_DISABLED_ACK"
    ) != "1":
        failures.append("lights-out mode lacks the disabled-usage-credits acknowledgement")
    return failures


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    failures = verify_no_paid_usage(root)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("PASS: Max OAuth only; paid usage and usage credits remain forbidden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
