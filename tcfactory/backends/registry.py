"""Fail-closed construction of configured executor backends."""

from __future__ import annotations

from collections.abc import Callable

from tcfactory.backends.base import EngineeringAgentBackend
from tcfactory.backends.claude import ClaudeBackend, ClaudeCredentialProvider
from tcfactory.v3.configuration import ExecutorBackend, ExecutorConfig

BackendBuilder = Callable[[ExecutorBackend], EngineeringAgentBackend]


def _build_claude(config: ExecutorBackend) -> EngineeringAgentBackend:
    return ClaudeBackend(
        ClaudeCredentialProvider(require_long_lived_token=True),
        max_concurrent_sessions=config.max_concurrent_sessions,
    )


_ALLOWED_ADAPTERS: dict[str, tuple[str, BackendBuilder]] = {
    "tcfactory.backends.claude.ClaudeBackend": ("claude", _build_claude),
}


def _require_backend_protocol(candidate: object) -> EngineeringAgentBackend:
    if not isinstance(candidate, EngineeringAgentBackend):
        raise RuntimeError("configured executor does not satisfy the backend protocol")
    return candidate


def _backend_capabilities(backend: EngineeringAgentBackend) -> set[str]:
    report = backend.capabilities()
    capabilities: set[str] = set()
    tools = set(report.allowed_tools)
    if {"Read", "Glob", "Grep"}.issubset(tools):
        capabilities.add("repository_read")
    if {"Write", "Edit"}.issubset(tools):
        capabilities.add("bounded_repository_write")
    if "Bash" in tools and report.bash_argument_allowlist:
        capabilities.add("deterministic_gate_execution")
    return capabilities


def resolve_executor_backend(config: ExecutorConfig) -> EngineeringAgentBackend:
    """Resolve the enabled default backend through a closed, audited allowlist."""

    backend_name = config.default_backend
    backend_config = config.backends.get(backend_name)
    if backend_config is None:
        raise RuntimeError("configured default executor backend is unknown")
    if not backend_config.enabled:
        raise RuntimeError("configured default executor backend is disabled")
    allowed = _ALLOWED_ADAPTERS.get(backend_config.adapter)
    if allowed is None:
        raise RuntimeError("configured executor adapter is not allowlisted")
    expected_name, builder = allowed
    if backend_name != expected_name:
        raise RuntimeError("configured executor name does not match its allowlisted adapter")
    backend = _require_backend_protocol(builder(backend_config))
    report = backend.capabilities()
    if not report.network_denial or not report.sandbox:
        raise RuntimeError("configured executor weakens the required execution boundary")
    actual = _backend_capabilities(backend)
    configured = set(backend_config.capabilities)
    if configured != actual:
        raise RuntimeError("configured executor capabilities do not match the adapter")
    return backend


__all__ = ["resolve_executor_backend"]
