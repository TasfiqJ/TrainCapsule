from __future__ import annotations

import os
from pathlib import Path

import yaml

DISALLOWED_BILLING_ENV = {
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
}


def verify_no_paid_usage(root: Path) -> list[str]:
    failures: list[str] = []
    factory = yaml.safe_load((root / "config/factory.yaml").read_text(encoding="utf-8"))
    autonomy = yaml.safe_load((root / "config/autonomy.yaml").read_text(encoding="utf-8"))
    auth_source = (root / "tcfactory/auth.py").read_text(encoding="utf-8")

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
