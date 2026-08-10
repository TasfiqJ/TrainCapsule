#!/usr/bin/env python3
"""Deterministic oracle for the T001 evidence ledger itself.

verify_precedence.py checks the normative behaviours NB1-NB5 over the bundle bytes.
This checker covers the separate failure mode that produced the previous non-pass
verdict: an evidence ledger whose recorded measurement commit had gone stale while
normative artifacts kept changing, so its PASS readings no longer described the
committed tree.

Invariants (all machine-checked, no narrative input):

  EC1  ledger base_sha resolves in this repository and is HEAD or an ancestor of HEAD.
  EC2  every path changed between base_sha and HEAD is evidence-only, so no normative
       artifact moved after the readings were taken.
  EC3  every path in outputs and raw_evidence_paths exists on disk.
  EC4  truth-state vocabulary is closed, and no gate recorded PASS with exit_code != 0.
  EC5  no non-pass truth state (UNKNOWN, SKIPPED, INFRASTRUCTURE_ERROR, INVALID_ORACLE,
       UNATTRIBUTED, EXTERNAL_VALIDATION_REQUIRED) is aggregated into a pass claim.

Usage:
  python3 docs/evidence/T001/verify_evidence_currency.py              # check the real ledger
  python3 docs/evidence/T001/verify_evidence_currency.py --self-test  # negative control

Exit code 0 means every invariant held. Exit code 1 means at least one failed.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

Ledger = dict[str, Any]
Mutation = tuple[str, str, Callable[[Ledger], None]]
Result = tuple[str, bool, str]

ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / ".factory/external-evidence/T001.json"

# Paths that may legitimately change after a reading without invalidating it.
EVIDENCE_ONLY_PREFIXES = (
    ".factory/external-evidence/T001.json",
    "docs/evidence/T001/",
)

NON_PASS_STATES = {
    "UNKNOWN",
    "SKIPPED",
    "INFRASTRUCTURE_ERROR",
    "INVALID_ORACLE",
    "UNATTRIBUTED",
    "EXTERNAL_VALIDATION_REQUIRED",
    "FAIL",
}
ALLOWED_STATES = NON_PASS_STATES | {"PASS"}


def git(*args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def collect_states(node: object, path: str = "") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        mapping = cast(dict[str, Any], node)
        for key, value in mapping.items():
            if key == "truth_state" and isinstance(value, str):
                found.append((f"{path}.{key}", value))
            found.extend(collect_states(value, f"{path}.{key}"))
    elif isinstance(node, list):
        items = cast(list[Any], node)
        for index, value in enumerate(items):
            found.extend(collect_states(value, f"{path}[{index}]"))
    return found


def check(ledger: Ledger, head: str) -> list[Result]:
    """Return (invariant_id, ok, detail) for every invariant."""
    results: list[Result] = []

    base = str(ledger.get("base_sha", ""))
    code, _ = git("cat-file", "-e", f"{base}^{{commit}}")
    resolves = code == 0
    if resolves and base != head:
        is_ancestor = base in git("rev-list", head)[1].split()
    else:
        is_ancestor = resolves
    results.append(
        (
            "EC1",
            resolves and is_ancestor,
            f"base_sha={base[:12]} resolves={resolves} "
            f"is_head_or_ancestor={is_ancestor} head={head[:12]}",
        )
    )

    if resolves and is_ancestor:
        changed = [p for p in git("diff", "--name-only", base, head)[1].splitlines() if p]
        stray = [p for p in changed if not p.startswith(EVIDENCE_ONLY_PREFIXES)]
        results.append(
            (
                "EC2",
                not stray,
                f"{len(changed)} path(s) changed since base_sha, "
                f"{len(stray)} outside evidence-only scope: {stray}",
            )
        )
    else:
        results.append(("EC2", False, "not evaluated: EC1 failed, range is undefined"))

    declared: list[str] = [
        str(item)
        for key in ("outputs", "raw_evidence_paths")
        for item in ledger.get(key, [])
    ]
    missing = [p for p in declared if not (ROOT / p).exists()]
    results.append(
        ("EC3", not missing, f"{len(declared)} declared path(s), missing={missing}")
    )

    states = collect_states(ledger)
    bad_vocab = [f"{p}={v}" for p, v in states if v.upper() not in ALLOWED_STATES]
    gates: list[Ledger] = list(ledger.get("machine_gates", []))
    lying_gates: list[str] = [
        str(gate.get("name", "?"))
        for gate in gates
        if str(gate.get("truth_state", "")).upper() == "PASS" and gate.get("exit_code") != 0
    ]
    results.append(
        (
            "EC4",
            not bad_vocab and not lying_gates,
            f"{len(states)} truth_state field(s), unknown_vocabulary={bad_vocab}, "
            f"pass_with_nonzero_exit={lying_gates}",
        )
    )

    behaviors: list[Ledger] = list(ledger.get("normative_behaviors", []))
    non_pass_ids: set[str] = {
        str(behavior.get("id", ""))
        for behavior in behaviors
        if str(behavior.get("truth_state", "")).upper() in NON_PASS_STATES
    }
    aggregate = json.dumps(
        {
            k: v
            for k, v in ledger.items()
            if k.startswith("overall_truth_state") or k == "value_assessment"
        }
    )
    flattened = aggregate.replace("-", " ").replace(",", " ")
    leaked: list[str] = sorted(
        i for i in non_pass_ids if i and f"{i} PASS" in flattened
    )
    results.append(
        (
            "EC5",
            not leaked,
            f"non_pass_behaviors={sorted(i for i in non_pass_ids if i)}, "
            f"aggregated_as_pass={leaked}",
        )
    )
    return results


def run(ledger: Ledger, head: str, label: str) -> bool:
    results = check(ledger, head)
    print(f"--- {label} ---")
    for name, ok, detail in results:
        print(f"{name}: {'PASS' if ok else 'FAIL'} - {detail}")
    return all(ok for _, ok, _ in results)


def self_test(ledger: Ledger, head: str) -> int:
    """Negative control: each mutation must break exactly its target invariant."""
    cases: list[Mutation] = [
        ("EC1", "base_sha points at a commit that is not an ancestor of HEAD",
         lambda d: d.update({"base_sha": "0" * 40})),
        ("EC3", "a declared output path is replaced with a nonexistent file",
         lambda d: d["outputs"].append("docs/evidence/T001/does_not_exist.md")),
        ("EC4", "a gate claims PASS while recording a nonzero exit code",
         lambda d: d["machine_gates"][0].update({"exit_code": 1})),
        ("EC4", "a truth_state uses a value outside the closed vocabulary",
         lambda d: d["normative_behaviors"][0].update({"truth_state": "MOSTLY_PASS"})),
        ("EC5", "an UNKNOWN behaviour is aggregated into the pass summary",
         lambda d: d["overall_truth_state_current"].update(
             {"normative_behaviors": "NB1-NB5 PASS"})),
    ]
    detected = 0
    for target, description, mutate in cases:
        mutated = copy.deepcopy(ledger)
        mutate(mutated)
        results: dict[str, bool] = {name: ok for name, ok, _ in check(mutated, head)}
        fired = not results.get(target, True)
        print(f"[{target}] {description}: {'DETECTED' if fired else 'MISSED'}")
        detected += int(fired)
    ok = detected == len(cases)
    print(
        f"RESULT: {'PASS' if ok else 'FAIL'} - {detected} of {len(cases)} "
        "targeted mutations were detected"
    )
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    head = git("rev-parse", "HEAD")[1]
    ledger: Ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    if "--self-test" in argv:
        return self_test(ledger, head)
    ok = run(ledger, head, f"T001 evidence ledger at HEAD {head[:12]}")
    print(f"RESULT: {'PASS' if ok else 'FAIL'} - evidence currency invariants EC1-EC5")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
