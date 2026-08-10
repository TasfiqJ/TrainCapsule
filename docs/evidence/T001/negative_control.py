#!/usr/bin/env python3
"""Negative control for docs/evidence/T001/verify_precedence.py.

Read-only with respect to this repository. For each normative behavior NB1-NB5 it builds a
throwaway mirror of the inputs under a temporary directory, corrupts exactly one input in that
mirror, runs the verifier against the mirror, and requires that the verifier's report for the
targeted behavior changes and that the verifier exits non-zero.

Run from the repository root:

    python3 docs/evidence/T001/negative_control.py

Exit 0 means every one of the five mutations was detected, so a PASS from the verifier is not
vacuous. Exit 1 means at least one mutation went undetected, which invalidates the verifier as an
oracle. The repository bundle, the manifests and SOURCE_PRECEDENCE.md are never written to; only
copies inside the temporary mirror are modified.
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MIRRORED = [
    "docs/source-of-truth/final-2026-08-09",
    "docs/evidence/T001",
    ".factory/source-locks",
]


def build_mirror(dst: Path) -> None:
    """Copy every input the verifier reads into `dst`, preserving repository-relative layout."""
    for rel in MIRRORED:
        shutil.copytree(ROOT / rel, dst / rel)
    shutil.copy2(ROOT / "SOURCE_PRECEDENCE.md", dst / "SOURCE_PRECEDENCE.md")


def replace_first_digest(path: Path, needle: str) -> str:
    """Zero the digest on the first line of a sha256sum file whose name part contains `needle`."""
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        digest, sep, name = line.partition("  ")
        if sep and needle in name:
            lines[i] = "0" * len(digest) + "  " + name
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return name
    raise SystemExit(f"negative control could not find {needle!r} in {path}")


def mutate_nb1(m: Path) -> str:
    name = replace_first_digest(m / "docs/evidence/T001/final_bundle.sha256", "EXECUTIVE")
    return f"zeroed the recorded digest of {name} in the mirrored final_bundle.sha256"


def mutate_nb2(m: Path) -> str:
    lock = m / ".factory/source-locks/FINAL_MANIFEST.json"
    lock.write_text(lock.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    return "appended one newline to the mirrored .factory/source-locks/FINAL_MANIFEST.json copy"


def mutate_nb3(m: Path) -> str:
    manifest = m / "docs/source-of-truth/final-2026-08-09/FINAL_MANIFEST.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    order = data["authority_order"]
    order[0], order[1] = order[1], order[0]
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return "swapped the first two entries of authority_order in the mirrored FINAL_MANIFEST.json"


def mutate_nb4(m: Path) -> str:
    dup = m / "docs/source-of-truth/final-2026-08-09/08_ACQUISITION_THESIS(1).md"
    dup.write_bytes(dup.read_bytes() + b"\n")
    return "appended one newline to the mirrored 08_ACQUISITION_THESIS(1).md duplicate"


def mutate_nb5(m: Path) -> str:
    readme = m / "docs/source-of-truth/final-2026-08-09/README.md"
    text = readme.read_text(encoding="utf-8")
    mutated = text.replace("TRAINCAPSULE_FINAL_MASTER_PLAN.md", "SOME_OTHER_DOCUMENT.md", 1)
    if mutated == text:
        raise SystemExit("negative control could not alter the recorded NB5 divergence")
    readme.write_text(mutated, encoding="utf-8")
    return "renamed the recorded NB5 divergence entry in the mirrored README.md read order"


MUTATIONS = [
    ("NB1", mutate_nb1),
    ("NB2", mutate_nb2),
    ("NB3", mutate_nb3),
    ("NB4", mutate_nb4),
    ("NB5", mutate_nb5),
]


def run_verifier(root: Path) -> tuple[int, dict[str, str]]:
    """Run the verifier copy under `root` and return its exit code and per-NB report lines."""
    proc = subprocess.run(
        [sys.executable, str(root / "docs/evidence/T001/verify_precedence.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    report: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        match = re.match(r"^(NB[1-5]): (.*)$", line)
        if match:
            report[match.group(1)] = match.group(2)
    if len(report) != 5:
        raise SystemExit(f"verifier did not report five behaviors: {proc.stdout}{proc.stderr}")
    return proc.returncode, report


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="t001_negative_control_") as tmp:
        baseline_root = Path(tmp) / "baseline"
        build_mirror(baseline_root)
        baseline_code, baseline = run_verifier(baseline_root)
        print(f"baseline (unmutated mirror): exit_code={baseline_code}")
        for nb, _state in sorted(baseline.items()):
            print(f"  baseline {nb}: {_state}")
        if baseline_code != 0:
            print("RESULT: INVALID_ORACLE - the unmutated mirror does not reproduce the baseline")
            return 1

        undetected: list[str] = []
        for nb, mutate in MUTATIONS:
            mirror = Path(tmp) / f"mutated_{nb}"
            build_mirror(mirror)
            description = mutate(mirror)
            code, report = run_verifier(mirror)
            changed = sorted(k for k in report if report[k] != baseline[k])
            detected = code != 0 and nb in changed
            print(f"{nb}: {description}")
            print(f"  exit_code={code} changed={changed} targeted_detected={detected}")
            print(f"  {nb} now: {report[nb]}")
            if not detected:
                undetected.append(nb)

    if undetected:
        print(f"RESULT: FAIL - mutations not detected: {undetected}")
        return 1
    print("RESULT: PASS - all 5 single-input mutations were detected and forced exit_code 1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
