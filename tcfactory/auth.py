from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Literal, cast

AuthSource = Literal["oauth_env", "subscription_login"]

# Any of these would route the factory away from the operator's Claude subscription.
DISALLOWED_ENV_VARS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
)

_ALLOWED_AUTH_METHODS = {"claude.ai", "oauth_token"}
_ALLOWED_API_PROVIDERS = {"", "firstParty", "first_party", "anthropic"}


def claude_config_dir() -> Path:
    override = os.getenv("CLAUDE_CONFIG_DIR")
    return Path(override).expanduser() if override else Path.home() / ".claude"


def claude_sandbox_state_environment() -> dict[str, str]:
    """Pin a writable, internally consistent Claude home and config directory."""

    config_dir = claude_config_dir().resolve()
    return {
        "HOME": str(config_dir.parent),
        "CLAUDE_CONFIG_DIR": str(config_dir),
    }


def subprocess_env_scrub_value(*, read_only: bool) -> str:
    """Use the native sandbox credential policy instead of the broken extra scrubber."""

    del read_only
    return "0"


def subscription_credentials_path() -> Path:
    return claude_config_dir() / ".credentials.json"


def _contains_key(value: Any, target: str) -> bool:
    if isinstance(value, dict):
        typed_value = cast(dict[object, object], value)
        return target in typed_value or any(
            _contains_key(item, target) for item in typed_value.values()
        )
    if isinstance(value, list):
        return any(_contains_key(item, target) for item in cast(list[object], value))
    return False


def configured_api_key_helpers() -> list[Path]:
    """Return readable Claude settings files that configure apiKeyHelper."""
    candidates = {
        claude_config_dir() / "settings.json",
        claude_config_dir() / "settings.local.json",
        Path.home() / ".claude.json",
        Path.cwd() / ".claude" / "settings.json",
        Path.cwd() / ".claude" / "settings.local.json",
    }
    found: list[Path] = []
    for path in sorted(candidates):
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if _contains_key(payload, "apiKeyHelper"):
            found.append(path)
    return found


def oauth_token_file_path() -> Path | None:
    """Return the operator-owned long-lived OAuth token file when configured.

    The token file lives outside the repository. Keeping only its pathname in the
    process environment lets a long-running autopilot reload a renewed one-year
    subscription token without restarting or exposing the token in task artifacts.
    """

    configured = os.getenv("TCF_CLAUDE_OAUTH_TOKEN_FILE")
    if configured:
        return Path(configured).expanduser()
    default = Path.home() / ".config" / "traincapsule" / "claude-oauth-token"
    return default if default.is_file() else None


def assert_secure_oauth_token_file() -> Path:
    """Require the lights-out token to live in a private regular file.

    The controller needs the token, but builder/reviewer Bash subprocesses do not.
    File mode 600 (or stricter) prevents accidental access by other local users.
    """

    path = oauth_token_file_path()
    if path is None or not path.exists():
        raise RuntimeError(
            "Lights-out mode requires a token file created from `claude setup-token` by "
            "scripts/configure_max5_token.sh. "
            "The file must exist outside the repository and be referenced by "
            "TCF_CLAUDE_OAUTH_TOKEN_FILE."
        )
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"Claude subscription OAuth token path must be a regular file: {path}")
    stat = path.stat()
    if hasattr(os, "getuid") and stat.st_uid != os.getuid():
        raise RuntimeError(
            f"Claude subscription OAuth token file is not owned by the current WSL user: {path}"
        )
    mode = stat.st_mode & 0o777
    if mode & 0o077:
        raise RuntimeError(
            f"Claude subscription OAuth token file {path} has unsafe permissions "
            f"{mode:03o}; run `chmod 600 {path}` and retry."
        )
    if not path.read_text(encoding="utf-8").strip():
        raise RuntimeError(f"Claude subscription OAuth token file is empty: {path}")
    return path


def refresh_subscription_oauth_token() -> bool:
    """Atomically refresh CLAUDE_CODE_OAUTH_TOKEN from its protected token file.

    Returns True when a non-empty token was loaded. The token value is never logged.
    This is called before every authentication check, so replacing the file after a
    future `claude setup-token` renewal is enough for a waiting autopilot to resume.
    """

    path = oauth_token_file_path()
    if path is None or not path.exists():
        return bool(os.getenv("CLAUDE_CODE_OAUTH_TOKEN"))
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError:
        return bool(os.getenv("CLAUDE_CODE_OAUTH_TOKEN"))
    if not token:
        return bool(os.getenv("CLAUDE_CODE_OAUTH_TOKEN"))
    os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = token
    return True


# Common provider and CI secrets are deliberately removed from Claude child processes.
# The only model credential retained is CLAUDE_CODE_OAUTH_TOKEN, which is subscription OAuth.
_AGENT_SECRET_ENV_VARS: tuple[str, ...] = (
    # Controller-only paths and hidden-gate handles must not enter model subprocesses.
    "TCF_PRIVATE_GATE_RUNNER",
    "TCF_CLAUDE_OAUTH_TOKEN_FILE",
    "TCF_ENV_FILE",
    "TCF_USAGE_CREDITS_DISABLED_ACK",
    "OPENAI_API_KEY",
    "COHERE_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "HF_TOKEN",
    "HUGGING_FACE_HUB_TOKEN",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AZURE_CLIENT_SECRET",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "DOCKER_AUTH_CONFIG",
)


def sanitized_agent_environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return a usable child environment without alternate billing routes or secrets.

    ClaudeAgentOptions.env is treated as an explicit subprocess environment by some SDK
    versions. Start from the current process so PATH, HOME, locale, Git, uv, and WSL
    integration continue to work, then remove credentials that a coding agent must not
    inherit. The long-lived Claude subscription OAuth token is retained intentionally.
    """
    refresh_subscription_oauth_token()
    environment = dict(os.environ)
    for name in (*DISALLOWED_ENV_VARS, *_AGENT_SECRET_ENV_VARS):
        environment.pop(name, None)
    # Never let a generic API key helper override subscription OAuth in child sessions.
    environment.pop("ANTHROPIC_CUSTOM_HEADERS", None)
    if extra:
        environment.update(extra)
    return environment


def assert_project_sandbox_credential_boundary(project_root: Path) -> None:
    """Fail closed unless Bash keeps the controller OAuth credential unreachable.

    Claude Code's optional subprocess environment scrubber currently fails to build its
    bubblewrap mount tree for service accounts.  The native sandbox can provide the same
    credential boundary, but only when the project policy is present and strict.  Check
    that policy before a session is allowed to opt out of the broken extra scrubber.
    """

    settings_path = project_root.resolve() / ".claude" / "settings.json"
    try:
        parsed = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Claude sandbox credential policy is missing or invalid: {settings_path}"
        ) from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Claude sandbox credential policy is invalid: {settings_path}")
    settings = cast(dict[str, object], parsed)
    sandbox_value = settings.get("sandbox")
    if not isinstance(sandbox_value, dict):
        raise RuntimeError(f"Claude sandbox credential policy is invalid: {settings_path}")
    sandbox = cast(dict[str, object], sandbox_value)
    credential_value = sandbox.get("credentials")
    if not isinstance(credential_value, dict):
        raise RuntimeError(f"Claude sandbox credential policy is invalid: {settings_path}")
    credential_policy = cast(dict[str, object], credential_value)

    def denied_values(value: object, *, key: str) -> set[str]:
        if not isinstance(value, list):
            return set()
        denied: set[str] = set()
        for entry in cast(list[object], value):
            if not isinstance(entry, dict):
                continue
            item = cast(dict[str, object], entry)
            candidate = item.get(key)
            if item.get("mode") == "deny" and isinstance(candidate, str):
                denied.add(candidate)
        return denied

    denied_environment = denied_values(credential_policy.get("envVars"), key="name")
    denied_files = denied_values(credential_policy.get("files"), key="path")
    boundary_is_strict = (
        sandbox.get("enabled") is True
        and sandbox.get("failIfUnavailable") is True
        and sandbox.get("allowUnsandboxedCommands") is False
        and "CLAUDE_CODE_OAUTH_TOKEN" in denied_environment
        and "~/.config/traincapsule/claude-oauth-token" in denied_files
        and "~/.claude/.credentials.json" in denied_files
    )
    if not boundary_is_strict:
        raise RuntimeError(
            "Claude sandbox credential policy must deny OAuth environment and files, "
            "fail when unavailable, and forbid unsandboxed commands"
        )


def active_subscription_auth_source() -> AuthSource | None:
    refresh_subscription_oauth_token()
    if os.getenv("CLAUDE_CODE_OAUTH_TOKEN"):
        return "oauth_env"
    if subscription_credentials_path().is_file():
        return "subscription_login"
    return None


def read_claude_auth_status() -> dict[str, Any]:
    """Read Claude Code's non-secret authentication status.

    The command prints account metadata, not the OAuth token itself. Max-only mode
    requires the standalone Claude Code executable so authentication can be verified
    rather than inferred merely from a credentials-file pathname.
    """
    executable = shutil.which("claude")
    if not executable:
        raise RuntimeError(
            "Max-only authentication cannot be verified because `claude` is not installed "
            "inside this WSL distribution. Install Claude Code, then run `claude auth login`."
        )
    completed = subprocess.run(
        [executable, "auth", "status"],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(
            "Claude Code is not authenticated with the Max subscription. Run `claude auth "
            "logout`, then `claude auth login`, choose Claude.ai rather than Console, and "
            f"retry. Status detail: {detail or 'unavailable'}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "`claude auth status` did not return valid JSON; update Claude Code and retry."
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError("`claude auth status` returned an unexpected payload.")
    return cast(dict[str, Any], payload)


def assert_max_oauth_only(*, require_long_lived_token: bool = False) -> AuthSource:
    """Fail closed unless authentication is Claude subscription OAuth only.

    Credential contents are never read or printed. This validates that no known API,
    gateway, or cloud-provider override is active and that Claude Code reports a
    Claude.ai/OAuth login. The operator must still verify the Max 5x tier in
    Claude Settings -> Usage because CLI tier metadata may be missing or stale.
    """
    disallowed = sorted(name for name in DISALLOWED_ENV_VARS if os.getenv(name))
    if disallowed:
        raise RuntimeError(
            "Max-only authentication refused because non-subscription routing variables "
            f"are set: {', '.join(disallowed)}. Unset them, run `claude auth logout`, then "
            "`claude auth login`, choose Claude.ai, and verify `claude auth status --text`."
        )

    helpers = configured_api_key_helpers()
    if helpers:
        raise RuntimeError(
            "Max-only authentication refused because apiKeyHelper is configured in: "
            + ", ".join(str(path) for path in helpers)
            + ". Remove or disable it for this WSL user and project."
        )

    if require_long_lived_token:
        assert_secure_oauth_token_file()
        if os.getenv("TCF_USAGE_CREDITS_DISABLED_ACK") != "1":
            raise RuntimeError(
                "Lights-out mode requires explicit confirmation that Claude usage credits "
                "are disabled. Rerun scripts/configure_max5_token.sh after disabling them "
                "in Claude Settings -> Usage."
            )
    source = active_subscription_auth_source()
    if require_long_lived_token and source != "oauth_env":
        raise RuntimeError(
            "Lights-out mode requires CLAUDE_CODE_OAUTH_TOKEN generated by "
            "`claude setup-token`. This is a long-lived Claude subscription OAuth token, "
            "not an Anthropic API key. Store it only in "
            "~/.config/traincapsule/claude-oauth-token with mode 600. The autopilot "
            "reloads that file before each retry; keep usage credits disabled."
        )
    if source is None:
        raise RuntimeError(
            "No Claude subscription OAuth credential was found. In WSL run `claude auth "
            "logout`, then `claude auth login`, choose Claude.ai, and verify `claude auth "
            "status --text`. Do not set ANTHROPIC_API_KEY."
        )

    status = read_claude_auth_status()
    if status.get("loggedIn") is not True:
        raise RuntimeError(
            "Claude Code reports that it is not logged in. Run `claude auth login` with the "
            "Claude.ai account that owns Max 5x."
        )
    auth_method = str(status.get("authMethod") or "")
    if auth_method not in _ALLOWED_AUTH_METHODS:
        raise RuntimeError(
            f"Max-only authentication refused because authMethod={auth_method!r}. Run "
            "`claude auth logout`, then `claude auth login`, and choose Claude.ai rather "
            "than Anthropic Console."
        )
    api_provider = str(status.get("apiProvider") or "")
    if api_provider not in _ALLOWED_API_PROVIDERS:
        raise RuntimeError(
            f"Max-only authentication refused because apiProvider={api_provider!r} is not "
            "the first-party Claude.ai route."
        )
    return source
