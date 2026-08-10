#!/usr/bin/env python3
"""Deterministic re-runnable oracle for the T001 normative behaviors NB1-NB5.

Read-only. No network, no credentials, no subprocess. Operates on repository bytes only.
Run from the repository root:

    python3 docs/evidence/T001/verify_precedence.py

Exit 0 means: NB1-NB4 measured PASS and the NB5 divergence is exactly the one recorded in
SOURCE_PRECEDENCE.md section 7. Exit 1 means at least one check is not in that state.

NB5 is never reported as PASS. Its truth state is UNKNOWN because the bundle does not say which
of the two lists is authoritative; this script only pins the divergence so that later drift in it
is detected instead of being silently absorbed.
"""

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
BUNDLE = ROOT / "docs/source-of-truth/final-2026-08-09"
EVIDENCE = ROOT / "docs/evidence/T001"

# The single divergence recorded in SOURCE_PRECEDENCE.md section 7, truth state UNKNOWN.
RECORDED_NB5_DIVERGENCE = ["TRAINCAPSULE_FINAL_MASTER_PLAN.md"]
DUPLICATE_PAIRS = [
    ("08_ACQUISITION_THESIS(1).md", "08_ACQUISITION_THESIS.md"),
    ("09_CAREER_AND_HIRING_THESIS(1).md", "09_CAREER_AND_HIRING_THESIS.md"),
    (
        "12_ROADMAP_BACKLOG_AND_MASTER_BUILD_PROMPT(1).md",
        "12_ROADMAP_BACKLOG_AND_MASTER_BUILD_PROMPT.md",
    ),
]

results: list[tuple[str, str, str]] = []


def record(check_id: str, truth_state: str, detail: str) -> None:
    results.append((check_id, truth_state, detail))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_sha256_file(path: Path) -> list[tuple[str, str]]:
    """Parse `sha256sum` output lines into [(digest, path_text)]."""
    entries: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        digest, _, name = line.partition("  ")
        entries.append((digest, name))
    return entries


def numbered_list(text: str, heading_pattern: str) -> list[str] | None:
    """Return the backticked filenames of the numbered list under the matching heading."""
    lines = text.splitlines()
    start: int | None = None
    for i, line in enumerate(lines):
        if line.startswith("#") and re.search(heading_pattern, line):
            start = i + 1
            break
    if start is None:
        return None
    out: list[str] = []
    for line in lines[start:]:
        if line.startswith("#"):
            break
        m = re.match(r"\s*\d+[.)]\s+`([^`]+)`", line)
        if m:
            out.append(m.group(1))
    return out


def manifest_field(field: str) -> list[str]:
    """Return a manifest field's entries (dict keys or list items) as text, order preserved."""
    data: dict[str, Any] = json.loads(
        (BUNDLE / "FINAL_MANIFEST.json").read_text(encoding="utf-8")
    )
    return [str(name) for name in data[field]]


def check_nb1() -> None:
    """Every manifest-locked bundle file matches its recorded SHA-256."""
    entries = parse_sha256_file(EVIDENCE / "final_bundle.sha256")
    bad: list[str] = []
    for digest, name in entries:
        target = BUNDLE / name
        if not target.is_file():
            bad.append(f"{name}: MISSING")
        elif sha256(target) != digest:
            bad.append(f"{name}: FAILED")
    locked = set(manifest_field("files"))
    recorded = {name for _, name in entries}
    if locked != recorded:
        bad.append(f"digest file does not cover the manifest files map: {locked ^ recorded}")
    state = "PASS" if not bad else "FAIL"
    detail = f"{len(entries) - len(bad)} of {len(entries)} OK"
    record("NB1", state, detail + (f"; {bad}" if bad else ""))


def check_nb2() -> None:
    """The manifest excludes itself; the docs copy and the source-lock copy are byte-identical."""
    bad: list[str] = []
    for digest, name in parse_sha256_file(EVIDENCE / "manifest_copies.sha256"):
        target = ROOT / name
        if not target.is_file():
            bad.append(f"{name}: MISSING")
        elif sha256(target) != digest:
            bad.append(f"{name}: FAILED")
    locked = manifest_field("files")
    if "FINAL_MANIFEST.json" in locked:
        bad.append("manifest lists itself in files")
    if len(locked) != 20:
        bad.append(f"expected 20 locked files, found {len(locked)}")
    state = "PASS" if not bad else "FAIL"
    detail = f"manifest files map = {len(locked)}, self-excluded"
    record("NB2", state, detail + (f"; {bad}" if bad else ""))


def check_nb3(authority_order: list[str]) -> None:
    """SOURCE_PRECEDENCE.md section 1 order equals FINAL_MANIFEST.authority_order."""
    declared = numbered_list(
        (ROOT / "SOURCE_PRECEDENCE.md").read_text(encoding="utf-8"), r"Authority order"
    )
    equal = declared == authority_order
    detail = f"declared={len(declared or [])} entries, equal={equal}"
    record("NB3", "PASS" if equal else "FAIL", detail)


def check_nb4() -> None:
    """The `(1)`-suffixed bundle files are byte-identical duplicates."""
    bad: list[str] = []
    for dup, base in DUPLICATE_PAIRS:
        dup_path, base_path = BUNDLE / dup, BUNDLE / base
        if not (dup_path.is_file() and base_path.is_file()):
            bad.append(f"{dup}: MISSING")
        elif sha256(dup_path) != sha256(base_path):
            bad.append(f"{dup}: DIVERGED from {base}")
    state = "PASS" if not bad else "FAIL"
    ok = len(DUPLICATE_PAIRS) - len(bad)
    detail = f"{ok} of {len(DUPLICATE_PAIRS)} pairs byte-identical"
    record("NB4", state, detail + (f"; {bad}" if bad else ""))


def check_nb5(authority_order: list[str]) -> bool:
    """README read order vs authority_order. Truth state is UNKNOWN by construction."""
    read_order = numbered_list((BUNDLE / "README.md").read_text(encoding="utf-8"), r"Read order")
    extra = [name for name in (read_order or []) if name not in authority_order]
    missing = [name for name in authority_order if name not in (read_order or [])]
    unchanged = extra == RECORDED_NB5_DIVERGENCE and not missing
    detail = (
        f"read_order={len(read_order or [])}, authority_order={len(authority_order)}, "
        f"extra_in_readme={extra}, missing_from_readme={missing}, "
        f"matches_recorded_discrepancy={unchanged}"
    )
    record("NB5", "UNKNOWN" if unchanged else "FAIL", detail)
    return unchanged


def main() -> int:
    authority_order = manifest_field("authority_order")
    check_nb1()
    check_nb2()
    check_nb3(authority_order)
    check_nb4()
    nb5_unchanged = check_nb5(authority_order)

    for check_id, state, detail in results:
        print(f"{check_id}: {state} - {detail}")

    failed = [c for c, s, _ in results if s == "FAIL"]
    print(f"pass_set={[c for c, s, _ in results if s == 'PASS']}")
    print("NB5 is UNKNOWN and is excluded from the pass set; see SOURCE_PRECEDENCE.md section 7.")
    if failed:
        print(f"RESULT: FAIL {failed}")
        return 1
    if not nb5_unchanged:
        print("RESULT: FAIL NB5 divergence differs from the recorded discrepancy")
        return 1
    print("RESULT: NB1-NB4 PASS, NB5 UNKNOWN and unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
