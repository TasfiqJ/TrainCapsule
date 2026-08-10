from __future__ import annotations

import re
from pathlib import Path

from gate_common import ROOT, tracked_and_untracked_files

SKIP_PARTS = {
    ".git",
    ".venv",
    "factory/artifacts",
    "factory/worktrees",
    "factory/logs",
    "node_modules",
    ".next",
    "dist",
    "build",
}
BINARY_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".whl",
    ".pyc",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".mp4",
    ".mov",
}
PATTERNS = {
    "Anthropic API key": re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    "GitHub classic token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "GitHub fine-grained token": re.compile(r"github_pat_[A-Za-z0-9_]{40,}"),
    "OpenAI API key": re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{30,}"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "Claude OAuth token assignment": re.compile(
        r"CLAUDE_CODE_OAUTH_TOKEN\s*=\s*['\"]?(?!\$|<|YOUR|REDACTED)[A-Za-z0-9_-]{24,}"
    ),
}


def skipped(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    return path.suffix.lower() in BINARY_SUFFIXES or any(part in rel for part in SKIP_PARTS)


def main() -> int:
    findings: list[str] = []
    for path in tracked_and_untracked_files():
        if skipped(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{path.relative_to(ROOT)}:{line}: {name}")
    if findings:
        print("Secret scan failed:")
        print("\n".join(findings))
        return 1
    print("PASS: no high-confidence credential pattern found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
