#!/usr/bin/env python3
"""Deterministically build the complete TrainCapsule V3.1-ZH authority generation."""
# ruff: noqa: E501

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GENERATION_ID = "traincapsule-v3.1-zh-2026-08-12"
GENERATED_AT = "2026-08-12T00:00:00Z"
ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "docs" / "source-of-truth" / "v3.1-zh-2026-08-12"
V3 = ROOT / "docs" / "source-of-truth" / "v3-2026-08-11"
BUNDLE = (
    ROOT
    / "TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11"
    / "traincapsule_v3_review_2026-08-11"
)
MANIFEST_PATH = HERE / "FINAL_MANIFEST_V3_1_ZH.json"
COVERAGE_PATH = HERE / "SECTION_COVERAGE_V3_TO_V3_1_ZH.json"


@dataclass(frozen=True)
class Document:
    source: Path
    target: str
    logical_id: str
    authority_class: str
    derived_from: str
    title: str


DOCUMENTS = (
    Document(V3 / "README.md", "README.md", "TC.V3_1_ZH.GENERATION_INDEX", "generation_index", "TC.V3.GENERATION_INDEX", "TrainCapsule V3.1-ZH source generation"),
    Document(V3 / "00_EXECUTIVE_BUILD_DECISION_V3.md", "00_EXECUTIVE_BUILD_DECISION_V3_1_ZH.md", "TC.V3_1_ZH.EXECUTIVE_DECISION", "root_policy", "TC.V3.EXECUTIVE_DECISION", "00 — Executive Build Decision V3.1-ZH"),
    Document(V3 / "03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md", "03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3_1_ZH.md", "TC.V3_1_ZH.PRODUCT_REQUIREMENTS", "normative_product", "TC.V3.PRODUCT_REQUIREMENTS", "03 — Product Strategy and Requirements V3.1-ZH"),
    Document(V3 / "04_TECHNICAL_ARCHITECTURE_V3.md", "04_TECHNICAL_ARCHITECTURE_V3_1_ZH.md", "TC.V3_1_ZH.TECHNICAL_ARCHITECTURE", "normative_architecture", "TC.V3.TECHNICAL_ARCHITECTURE", "04 — Technical Architecture V3.1-ZH"),
    Document(V3 / "05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md", "05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3_1_ZH.md", "TC.V3_1_ZH.TRUST_SPECIFICATION", "normative_trust", "TC.V3.TRUST_SPECIFICATION", "05 — Trust, Replay, Reduction, Recovery, and Capsule Specification V3.1-ZH"),
    Document(V3 / "06_COMMERCIAL_MODEL_AND_GTM_V3.md", "06_COMMERCIAL_MODEL_AND_GTM_V3_1_ZH.md", "TC.V3_1_ZH.COMMERCIAL_MODEL", "normative_commercial", "TC.V3.COMMERCIAL_MODEL", "06 — Commercial Model, Go-to-Market, and Validation Plan V3.1-ZH"),
    Document(V3 / "12_GATE_BASED_ROADMAP_AND_BACKLOG_V3.md", "12_GATE_BASED_ROADMAP_AND_BACKLOG_V3_1_ZH.md", "TC.V3_1_ZH.ROADMAP", "normative_roadmap", "TC.V3.ROADMAP", "12 — Gate-Based Roadmap and Backlog V3.1-ZH"),
    Document(V3 / "13_SOURCE_REGISTER_V3.md", "13_SOURCE_REGISTER_V3_1_ZH.md", "TC.V3_1_ZH.SOURCE_REGISTER", "current_fact_register", "TC.V3.SOURCE_REGISTER", "13 — Current Source and Competitive Register V3.1-ZH"),
    Document(V3 / "14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3.md", "14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3_1_ZH.md", "TC.V3_1_ZH.MASTER_BUILD_PROMPT", "normative_build", "TC.V3.MASTER_BUILD_PROMPT", "14 — Claude Code Master Build Prompt V3.1-ZH"),
    Document(V3 / "FACTORY_LOOP_REDESIGN_SPEC.md", "FACTORY_LOOP_REDESIGN_SPEC_V3_1_ZH.md", "TC.V3_1_ZH.FACTORY_LOOP", "normative_factory", "TC.V3.FACTORY_LOOP", "TrainCapsule Autonomous Factory and Business Loop Redesign Specification V3.1-ZH"),
    Document(BUNDLE / "SOURCE_OF_TRUTH_MIGRATION_PLAN.md", "SOURCE_OF_TRUTH_MIGRATION_PLAN_V3_1_ZH.md", "TC.V3_1_ZH.MIGRATION_PLAN", "normative_migration", "TC.V3.SOURCE_MIGRATION_PLAN", "Source-of-Truth Migration Plan V3.1-ZH"),
)


AMENDMENT = """
## V3.1-ZH controlling amendment

This document is a complete, self-contained V3.1-ZH derivation of the identified immutable V3
source. Every V3 section is preserved below in source order unless its heading/body is explicitly
superseded by the deterministic generation rules recorded in
`SECTION_COVERAGE_V3_TO_V3_1_ZH.json`. No runtime consumer may inherit normative clauses from the
historical V3 directory.

The controlling doctrine is `ZERO_FOUNDER_INTERVENTION_AFTER_BOOTSTRAP`. After one-time bootstrap,
no founder, operator, reviewer, or other person is a runtime approval or release dependency. There is
no human-approval runtime state. Missing machine authority is a scoped `BLOCKED_POLICY`; missing
outside facts are `WAITING_EXTERNAL`/`UNKNOWN` and block only dependent scope.

`B004` is critical and explicitly nonblocking: zero founder intervention is not a claim of literal
zero people. External people and organizations may asynchronously supply attributable conversations,
incident access, payment, adoption, independent-operation, acceptance, or other customer facts only
through authenticated external receipts. The loop may not fabricate those facts and must continue
all unrelated lanes while they are absent.

No AI session, candidate code, repository workflow, or mutable repository file may self-certify
trust, release, or activation. A separately administered off-repository machine verifier uses
protected policy, private oracles, signing keys, revocation state, and credentials to issue scoped,
expiring, revocable, non-replayable exact-SHA receipts. An unavailable or invalid authority fails
closed.

Release is frozen candidate → required local/private gates → valid independent machine-policy
receipt → race-checked non-force exact-SHA push to `main` → post-push hosted checks and exact-main
verification. Pull requests, candidate-branch publication, force push, deletion, bypass, and reuse
of another SHA's pass are forbidden. Controller activation requires a separate signed external
receipt binding the exact published SHA, environment, generation, controller, configuration,
policy, canaries, and expiry.

All original V3 laws for exact identity, evidence provenance, native-first and complete-substitute
comparison, explicit `UNKNOWN`, controlled-evidence ceilings, finite retry/recovery, bounded roadmap,
and truthful commercial claims remain mandatory. Controlled or synthetic fixtures cannot prove GPU,
customer, payment, adoption, independent-operation, external-value, or commercial-support facts.

This generation is a disclosed amendment, not a claim of exact original-V3 conformance. Replacing
qualified-person review with encoded independent machine policy loses contextual judgment that might
detect novel ambiguity outside declared policy/private oracles. Separation of authority, hidden
checks, scoped receipts, expiry, revocation, exact-SHA binding, complete evidence, fail-closed release,
and rollback reduce but do not eliminate that residual risk.

""".lstrip()


REPLACEMENTS = (
    ("HUMAN_REVIEWED_PROPERTY", "MACHINE_VERIFIED_PROPERTY"),
    ("REQUIRES_HUMAN_APPROVAL", "REQUIRES_MACHINE_POLICY"),
    ("ELIGIBLE_WITH_HUMAN_REVIEW", "ELIGIBLE_WITH_MACHINE_POLICY"),
    ("HUMAN_REVIEWER", "MACHINE_POLICY_VERIFIER"),
    ("WAITING_HUMAN", "BLOCKED_POLICY"),
    ("HUMAN_PROVIDED", "EXTERNAL_RECEIPT_PROVIDED"),
    ("HUMAN_REVIEW", "MACHINE_POLICY_ATTESTATION"),
    ("HumanApprovalRecord", "MachinePolicyReceipt"),
    ("humanApprovalForExpansion", "machinePolicyForExpansion"),
    ("roadmapExpansionRequiresHumanApproval", "roadmapExpansionRequiresMachinePolicy"),
    ("humanApprovalRequired", "machinePolicyReceiptRequired"),
    ("humanReviewAfterRepeat", "machinePolicyReviewAfterRepeat"),
    ("humanApprovals", "machinePolicyReceipts"),
    ("human-approval.json", "machine-policy-receipt.json"),
    ("no first-class human machine-policy receipt state", "no person-dependent approval state"),
    ("human machine-policy requests", "independent machine-policy requests"),
    ("`HUMAN`: create machine-policy request", "`MACHINE_POLICY`: request independent signed authorization"),
    ("human release machine authorization", "machine-policy release authorization"),
    ("authorized human policy", "authorized independent machine policy"),
    ("required human-machine-policy authorization policy", "required independent machine-policy authorization policy"),
    ("forge approval", "forge a signed machine-policy receipt"),
    ("approval is signed or stored in a trusted external location", "machine-policy receipt is signed and stored in the protected external authority root"),
    ("qualified-independent machine-policy authorization", "independent machine-policy authorization"),
    ("human_approval_packet.md", "machine_policy_request.md"),
    ("human_approval.yaml", "machine_authority.yaml"),
    ("human_gate.py", "machine_policy_gate.py"),
    ("Human approval boundary", "Independent machine authorization boundary"),
    ("Human approval state", "Machine-policy authorization state"),
    ("Human review and re-enable", "Machine authorization and activation"),
    ("Human authority", "Independent machine authority"),
    ("human authority", "independent machine authority"),
    ("Qualification of reviewer", "Qualification of independent verifier policy and private oracles"),
    ("The approval packet records why the reviewer is qualified", "The machine-policy request records why the verifier policy and private oracles are sufficient"),
    ("Multiple scoped approvals are preferred", "Multiple scoped signed machine-policy receipts are preferred"),
    ("reviewerQualification", "verifierPolicyQualification"),
    ("reviewer:", "verifierPolicyId:"),
    ("approvalId:", "receiptId:"),
    ("Approval fields:", "Machine-policy receipt fields:"),
    ("approval packets", "machine-policy requests"),
    ("approval packet", "machine-policy request"),
    ("trusted approval root", "protected machine-authority root"),
    ("approval root", "machine-authority root"),
    ("approval state", "machine-policy receipt state"),
    ("approval policy", "machine-policy authorization policy"),
    ("approval coordination", "machine-policy authorization coordination"),
    ("commercially supported pack approval", "commercially supported pack machine authorization"),
    ("commercial-pack approval", "commercial-pack machine authorization"),
    ("source-migration approval", "source-migration machine authorization"),
    ("scoped approval", "scoped signed receipt"),
    ("signed approval", "signed machine-policy receipt"),
    ("prevents unconditional approval", "prevents unconditional authorization"),
    ("unconditional approval", "unconditional authorization"),
    ("potential approval", "potential authorization"),
    ("comparative approval", "comparative authorization"),
    ("external use approval", "external-use machine authorization"),
    ("release approval", "release machine authorization"),
    ("reviewer and approval metadata", "verifier-policy and machine-receipt metadata"),
    ("required reviewer qualifications", "required verifier-policy and private-oracle coverage"),
    ("reviewer qualifications", "verifier-policy and private-oracle coverage"),
    ("forge a reviewer", "forge a verifier or receipt"),
    ("prepare an approval", "prepare a machine-policy request"),
    ("create the approval", "create the signed machine-policy receipt"),
    ("stale approval", "stale machine-policy receipt"),
    ("expired approval", "expired machine-policy receipt"),
    ("invalid or missing approval", "invalid or missing machine-policy receipt"),
    ("completion expansion requires approval", "completion expansion requires signed machine-policy authorization"),
    ("requires approval", "requires signed machine-policy authorization"),
    ("convert `UNKNOWN` into approval", "convert `UNKNOWN` into authorization"),
    ("blocks approval", "blocks authorization"),
    ("external or human evidence", "external evidence or independent machine-policy evidence"),
    ("human evidence", "independent machine-policy evidence"),
    ("human/external boundary", "machine-policy/external boundary"),
    ("human/external blockers", "machine-policy/external blockers"),
    ("external/human states", "external/machine-policy states"),
    ("human/external evidence", "machine-policy/external evidence"),
    ("human-review responsibility", "machine-policy responsibility"),
    ("human-reviewer/adviser plan", "independent-verifier/private-oracle plan"),
    ("PR/human release modes", "PR/machine-policy release modes"),
    ("PR/human policy", "PR/machine-policy policy"),
    ("human release approval current", "machine-policy release authorization current"),
    ("human trust/security review", "independent machine-policy trust/security evaluation"),
    ("Human approve", "Independent machine-policy authorize"),
    ("human approves", "independent machine policy authorizes"),
    ("founder/adviser reviews evidence", "independent verifier evaluates evidence"),
    ("founder intuition", "unverified intuition"),
    ("founder hours", "operator-independent automation hours"),
    ("founder network", "attributable source network"),
    ("founder dependence", "operator dependence"),
    ("founder delivery allocation", "automated delivery allocation"),
    ("Founder operating cadence", "Autonomous operating cadence"),
    ("founder learning/defense", "evidence-driven learning/defense"),
    ("bespoke founder consulting", "bespoke operator consulting"),
    ("founder/customer actions", "external/customer actions"),
    ("signed founder decision", "signed bounded machine-policy decision"),
    ("The founder or authorized product authority accepts/rejects each proposal.", "Independent bounded machine policy accepts or rejects each proposal."),
    ("the founder can understand the active decision", "status makes the active decision operator-readable"),
    ("`HUMAN`: create approval packet", "`MACHINE_POLICY`: request independent signed authorization"),
    ("optional second independent reviewer", "optional second independent private oracle"),
    ("Reviewers return proposals", "Independent evaluation roles return proposals"),
    ("Completion reviewers", "Completion evaluation roles"),
    ("completion reviewers", "completion evaluation roles"),
    ("completion reviewer", "completion evaluation role"),
    ("reviewer proposals", "evaluation-role proposals"),
    ("show external/human blockers separately", "show external/machine-policy blockers separately"),
    ("humanReview: waiting state", "machinePolicy: scoped BLOCKED_POLICY state"),
    ("Engineering completion may be automated for M0–M2, but M3–M6 depend on external or human evidence", "Engineering completion may be automated for M0–M2, but M3–M6 depend on attributable external evidence and independent machine-policy evidence"),
    ("required human-approval policy", "required independent machine-policy authorization"),
    ("require human decision", "require independent machine-policy decision"),
    ("scheduler, milestone, approval, evidence", "scheduler, milestone, machine-policy receipt, evidence"),
    ("do not enable auto-merge during migration", "enable auto-merge only after required exact-SHA checks and independent machine-policy authorization"),
    ("external/human states", "external/machine-policy states"),
    ("approval root is writable by AI", "machine-authority root is writable by candidate identities"),
    ("human/external evidence is unforgeable by AI roles", "machine-policy/external evidence is unforgeable by candidate identities"),
    ("signed human-approval model", "signed independent machine-policy receipt model"),
    ("Human approve case-specific", "Independent machine-policy authorize case-specific"),
    ("Human approve customer-facing", "Independent machine-policy authorize customer-facing"),
    ("Weekly founder review", "Weekly autonomous evidence review"),
    ("security reviewer", "security private-oracle policy"),
    ("adviser/reviewer availability", "private-oracle and verifier availability"),
    ("Contract security reviewer", "Contract security private-oracle policy"),
    ("distributed-training adviser/reviewer", "distributed-training private-oracle policy"),
    ("security/private-deployment reviewer", "security/private-deployment private-oracle policy"),
    ("The factory may prepare an approval packet. It may not create or forge approval.", "The factory may prepare a machine-policy request. It may not create or forge the signed receipt."),
    ("human trust/security review", "independent machine-policy trust/security evaluation"),
    ("founder or authorized product authority", "independent bounded machine policy"),
    ("approvals/", "machine-policy-receipts/"),
    ("- approvals;", "- machine-policy receipts;"),
    ("Approval scopes", "Machine-policy authorization scopes"),
    ("human/authorized auto-merge policy", "independent machine-policy authorization and automated merge policy"),
    ("qualified human pack approval", "independent machine-policy pack authorization"),
    ("qualified human trust approval", "independent machine-policy trust authorization"),
    ("qualified human approval", "independent machine-policy authorization"),
    ("qualified human reviewer", "independent machine-policy verifier"),
    ("qualified human", "independent machine authority"),
    ("Qualified human", "Independent machine authority"),
    ("Human approval", "Independent machine-policy authorization"),
    ("human approval", "independent machine-policy authorization"),
    ("Human review", "Machine-policy evaluation"),
    ("human review", "machine-policy evaluation"),
    ("Human reviewer", "Independent machine-policy verifier"),
    ("human reviewer", "independent machine-policy verifier"),
    ("human-approved", "machine-policy-authorized"),
    ("human pack approval", "machine-policy pack authorization"),
    ("founder/human decision", "independent machine-policy decision"),
    ("human-led outreach and sales", "policy-controlled outreach and attributable external sales actions"),
    ("A human records the final wedge decision.", "Independent signed machine policy records the final bounded wedge decision."),
    ("AI | FOUNDER | MACHINE_POLICY_VERIFIER | CUSTOMER | EXTERNAL_PARTY", "AI | MACHINE_POLICY_VERIFIER | CUSTOMER | EXTERNAL_PARTY"),
    ("PRODUCT | FACTORY | EXTERNAL | HUMAN", "PRODUCT | FACTORY | EXTERNAL | MACHINE_POLICY"),
    ("standard: false initially", "standard: true after required CI and a valid machine-policy receipt"),
    ("integration: false", "integration: true after required CI, private gates, and a valid machine-policy receipt"),
    ("trust_core: false", "trust_core: true after required CI, private oracles, and a valid machine-policy receipt"),
    ("integration/trust cannot auto-merge", "integration/trust auto-merge only after all required checks and a valid independent machine-policy receipt"),
    ("human and external evidence states", "machine-policy and external-evidence states"),
    ("human/external blockers", "machine-policy/external blockers"),
    ("external/human wait", "external/policy wait"),
    ("next human action", "next policy-controlled or external action"),
    ("human wait", "policy block"),
    ("human effort", "operator effort"),
    ("human expertise", "private-oracle and policy coverage"),
    ("human-readable", "operator-readable"),
    ("humanApproval", "machinePolicyReceipt"),
    # Cleanup after earlier compound replacements.
    ("human release machine authorization", "machine-policy release authorization"),
    ("human machine-policy", "independent machine-policy"),
    ("`HUMAN`: create machine-policy request", "`MACHINE_POLICY`: request independent signed authorization"),
    ("required human-machine-policy authorization policy", "required independent machine-policy authorization policy"),
    ("qualified-independent machine-policy authorization", "independent machine-policy authorization"),
    ("one operator other than the founder", "one independent external operator"),
    ("technical founder with meaningful training spend", "technical decision owner with meaningful training spend"),
    ("approval for external use", "machine-policy authorization for external use"),
    ("Secure customer approval", "Secure attributable customer authorization"),
    ("privacy/security approval", "attributable customer privacy authorization and machine-policy security authorization"),
)


TARGET_REPLACEMENTS: dict[str, tuple[tuple[str, str], ...]] = {
    "README.md": (
        ("active V3 authority", "active V3.1-ZH authority"),
        ("authorized on 11 August 2026", "authorized on 12 August 2026"),
        ("The migration base is:", "The immutable historical V3 migration base is:"),
        ("owner-directed machine-policy scope", "independent-machine-authority scope"),
        ("`13_SOURCE_REGISTER_V3.md`", "`13_SOURCE_REGISTER_V3_1_ZH.md`"),
        (
            "The repository owner's later zero-human directive replaces independent machine-policy authorization with candidate-bound deterministic machine-policy receipts; it does not replace required attributable external evidence.",
            "Independent machine-policy authorization remains mandatory and may be issued only by the separately administered off-repository verifier; candidate-bound deterministic local receipts cannot replace it or required attributable external evidence.",
        ),
        ("`FINAL_MANIFEST_V3.json`", "`FINAL_MANIFEST_V3_1_ZH.json`"),
        ("`scripts/generate_v3_manifest.py`", "`scripts/generate_v3_1_zh_source.py`"),
    ),
    "00_EXECUTIVE_BUILD_DECISION_V3_1_ZH.md": (
        ("V3 authority installed", "V3.1-ZH authority installed"),
    ),
    "12_GATE_BASED_ROADMAP_AND_BACKLOG_V3_1_ZH.md": (
        ("V3 source authority installed", "V3.1-ZH source authority installed"),
        ("Install V3 documents", "Install V3.1-ZH documents"),
        ("Enable V3 controller", "Enable V3.1-ZH controller"),
        ("V3 scheduler still", "V3.1-ZH scheduler still"),
        ("release uses pull requests;", "release uses exact-SHA ordinary non-force pushes to `main`;"),
        ("Change release path from direct main to draft PR", "Enforce receipt-authorized exact-SHA direct-main publication"),
        ("PR dry run, exact-SHA checks", "direct-main dry run, exact-SHA checks"),
    ),
    "FACTORY_LOOP_REDESIGN_SPEC_V3_1_ZH.md": (
        (
            "The factory can squash a candidate and fast-forward `main`, then push directly.",
            "The factory may push only the exact receipt-authorized candidate to `main` with a race check and a normal non-force fast-forward push.",
        ),
        ("releaseMode: PULL_REQUEST", "releaseMode: DIRECT_MAIN_EXACT_SHA"),
        ("releaseMode: pull_request", "releaseMode: direct_main_exact_sha"),
        ("directMainPush: false", "directMainPush: true"),
        ("Default to pull-request release.", "Use receipt-authorized exact-SHA direct-main release only."),
        ("→ draft PR", "→ ordinary non-force push to `main`"),
        ("integration/trust auto-merge only after all required checks and a valid independent machine-policy receipt", "integration/trust direct-main publication only after all required gates and a valid independent machine-policy receipt"),
        ("Install V3 authority", "Install V3.1-ZH authority"),
        ("gate-based V3 work items", "gate-based V3.1-ZH work items"),
    ),
    "SOURCE_OF_TRUTH_MIGRATION_PLAN_V3_1_ZH.md": (
        ("V3 product and factory strategy", "V3.1-ZH product and factory strategy"),
        ("docs/source-of-truth/v3-2026-08-11/", "docs/source-of-truth/v3.1-zh-2026-08-12/"),
        ("00_EXECUTIVE_BUILD_DECISION_V3.md", "00_EXECUTIVE_BUILD_DECISION_V3_1_ZH.md"),
        ("03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md", "03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3_1_ZH.md"),
        ("04_TECHNICAL_ARCHITECTURE_V3.md", "04_TECHNICAL_ARCHITECTURE_V3_1_ZH.md"),
        ("05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md", "05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3_1_ZH.md"),
        ("06_COMMERCIAL_MODEL_AND_GTM_V3.md", "06_COMMERCIAL_MODEL_AND_GTM_V3_1_ZH.md"),
        ("12_GATE_BASED_ROADMAP_AND_BACKLOG_V3.md", "12_GATE_BASED_ROADMAP_AND_BACKLOG_V3_1_ZH.md"),
        ("13_SOURCE_REGISTER_V3.md", "13_SOURCE_REGISTER_V3_1_ZH.md"),
        ("14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3.md", "14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3_1_ZH.md"),
        ("FACTORY_LOOP_REDESIGN_SPEC.md", "FACTORY_LOOP_REDESIGN_SPEC_V3_1_ZH.md"),
        ("FINAL_MANIFEST_V3.json", "FINAL_MANIFEST_V3_1_ZH.json"),
        ("`scripts/generate_v3_manifest.py`", "`scripts/generate_v3_1_zh_source.py`"),
        ("identify V3 as controlling", "identify V3.1-ZH as controlling"),
        ("active V3 authority", "active V3.1-ZH authority"),
        ("active V3 file", "active V3.1-ZH file"),
        ("active V3 bundle", "active V3.1-ZH bundle"),
        ("V3 context index", "V3.1-ZH context index"),
        ("after V3 authority exists", "after V3.1-ZH authority exists"),
        ("V3 scheduler runs", "V3.1-ZH scheduler runs"),
        ("V3 controller makes", "V3.1-ZH controller makes"),
        ("one canonical logical document in V3;", "one canonical logical document in V3.1-ZH;"),
        ("controls V3 scheduling", "controls V3.1-ZH scheduling"),
        ("explicit V3 work items", "explicit V3.1-ZH work items"),
        ("create V3 queue directories", "create V3.1-ZH queue directories"),
        ("write V3 state", "write V3.1-ZH state"),
        ("reference the V3 context resolver", "reference the V3.1-ZH context resolver"),
        ("stop V3 controller", "stop V3.1-ZH controller"),
        ("preserve V3 artifacts/logs", "preserve V3.1-ZH artifacts/logs"),
        ("Work on a dedicated branch and open a draft PR.", "Use the frozen exact-SHA candidate and publish only by an ordinary non-force push to `main`."),
        ("open draft PR;", "push the receipt-authorized exact SHA directly to `main`;"),
        ("enable auto-merge only after required exact-SHA checks and independent machine-policy authorization;", "push directly to `main` only after required exact-SHA gates and independent machine-policy authorization;"),
        ('"manifestVersion": 3', '"schemaVersion": 1'),
        ('"bundleVersion": "v3-2026-08-11"', f'"generationId": "{GENERATION_ID}"'),
        (
            '''  "migrationBaseSha": "...",
  "hashAlgorithm": "sha256",
  "canonicalization": {
    "textEncoding": "utf-8",
    "lineEndings": "lf",
    "trailingNewline": true
  },
  "files": [
    {
      "path": "...",
      "sha256": "...",
      "bytes": 0,
      "authorityClass": "normative"
    }
  ]''',
            '''  "authorityModel": {
    "machineAuthorityIndependentOffRepository": true,
    "releaseFlow": "DIRECT_MAIN_EXACT_SHA_MACHINE_RECEIPT_POST_PUSH_VERIFY"
  },
  "documents": [
    {
      "logicalId": "...",
      "path": "...",
      "sha256": "...",
      "authorityClass": "...",
      "generationId": "traincapsule-v3.1-zh-2026-08-12",
      "sections": []
    }
  ],
  "coverageEvidence": {
    "path": "docs/source-of-truth/v3.1-zh-2026-08-12/SECTION_COVERAGE_V3_TO_V3_1_ZH.json",
    "sha256": "..."
  },
  "integrity": {
    "algorithm": "sha256",
    "documentCount": 11,
    "manifestSelfIncluded": false,
    "generatorPath": "scripts/generate_v3_1_zh_source.py"
  }''',
        ),
    ),
    "14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3_1_ZH.md": (
        ("release through draft PR under current policy;", "release only through a receipt-authorized exact-SHA ordinary push to `main`;"),
    ),
}


FORBIDDEN_ACTIVE_SEMANTICS = (
    (
        "local receipts replacing independent machine authority",
        re.compile(
            r"owner(?:'s)? later zero-human directive replaces[^.\n]*"
            r"(?:independent machine-policy authorization|qualified-human approval)[^.\n]*"
            r"candidate-bound deterministic machine-policy receipts",
            re.IGNORECASE,
        ),
    ),
    ("owner-directive shadow authority", re.compile(r"owner-directed machine-policy scope", re.IGNORECASE)),
    ("reachable pull-request doctrine", re.compile(r"releaseMode:\s*pull_request", re.IGNORECASE)),
    ("stale active V3 register", re.compile(r"`13_SOURCE_REGISTER_V3\.md` is current factual authority", re.IGNORECASE)),
    ("stale active V3 manifest", re.compile(r"`FINAL_MANIFEST_V3\.json` is generated", re.IGNORECASE)),
    ("stale V3 generation creation", re.compile(r"Create:\s+```text\s+docs/source-of-truth/v3-2026-08-11/", re.IGNORECASE)),
    ("stale V3 controlling authority", re.compile(r"identify V3 as controlling", re.IGNORECASE)),
    ("stale active V3 authority", re.compile(r"\bactive V3 (?:authority|file|bundle)\b", re.IGNORECASE)),
    (
        "stale V3 operational instruction",
        re.compile(
            r"\b(?:controls|explicit|create|write|reference|stop|preserve)\s+(?:the\s+)?V3\s+"
            r"(?:scheduling|work items|queue directories|state|context resolver|controller|artifacts/logs)\b",
            re.IGNORECASE,
        ),
    ),
)


REQUIRED_TARGET_DOCTRINE: dict[str, tuple[str, ...]] = {
    "README.md": (
        "`13_SOURCE_REGISTER_V3_1_ZH.md` is current factual authority",
        "`FINAL_MANIFEST_V3_1_ZH.json` is generated by `scripts/generate_v3_1_zh_source.py`",
        "Independent machine-policy authorization remains mandatory",
    ),
    "SOURCE_OF_TRUTH_MIGRATION_PLAN_V3_1_ZH.md": (
        "docs/source-of-truth/v3.1-zh-2026-08-12/",
        "FINAL_MANIFEST_V3_1_ZH.json",
        "identify V3.1-ZH as controlling",
    ),
    "FACTORY_LOOP_REDESIGN_SPEC_V3_1_ZH.md": (
        "releaseMode: direct_main_exact_sha",
        "directMainPush: true",
    ),
}


def replace_policy(text: str, *, target: str | None = None) -> str:
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    if target is not None:
        for old, new in TARGET_REPLACEMENTS.get(target, ()):
            text = text.replace(old, new)
    return text


def headings(text: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    counters: dict[str, int] = {}
    stack: list[str] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if not match:
            continue
        level = len(match.group(1))
        title = match.group(2)
        stack = stack[: level - 1]
        stack.append(title)
        slug = re.sub(r"[^a-z0-9]+", "-", "-".join(stack).lower()).strip("-") or "root"
        counters[slug] = counters.get(slug, 0) + 1
        section_id = slug if counters[slug] == 1 else f"{slug}-{counters[slug]}"
        result.append({"sectionId": section_id, "heading": title, "level": level, "line": line_no})
    return result


def build_document(doc: Document) -> tuple[str, list[dict[str, Any]]]:
    source = doc.source.read_text(encoding="utf-8-sig")
    source_headings = headings(source)
    source_lines = source.splitlines()
    lines = source.splitlines()
    first_heading = next((i for i, line in enumerate(lines) if line.startswith("# ")), None)
    if first_heading is None:
        raise ValueError(f"source has no title heading: {doc.source}")
    lines[first_heading] = f"# {doc.title}"
    transformed_source = replace_policy("\n".join(lines).rstrip() + "\n", target=doc.target)
    metadata = (
        f"\n| Field | Value |\n|---|---|\n"
        f"| Logical ID | `{doc.logical_id}` |\n"
        f"| Generation | `{GENERATION_ID}` |\n"
        f"| Authority class | `{doc.authority_class}` |\n"
        f"| Derived from | `{doc.derived_from}` |\n\n"
    )
    target = transformed_source.splitlines()
    title_index = next(i for i, line in enumerate(target) if line.startswith("# "))
    target = "\n".join(target[: title_index + 1]) + metadata + AMENDMENT + "\n" + "\n".join(target[title_index + 1 :]).lstrip("\n") + "\n"
    target_headings = headings(target)
    transformed_source_titles = [
        replace_policy(item["heading"], target=doc.target) for item in source_headings
    ]
    coverage: list[dict[str, Any]] = []
    search_start = 0
    for source_index, (source_item, target_title) in enumerate(
        zip(source_headings, transformed_source_titles, strict=True)
    ):
        found = next((item for item in target_headings[search_start:] if item["heading"] == target_title), None)
        if found is None:
            if source_item is source_headings[0]:
                found = next(item for item in target_headings if item["heading"] == doc.title)
            else:
                raise ValueError(f"unmapped heading {source_item['heading']!r} in {doc.target}")
        search_start = target_headings.index(found) + 1
        section_start = source_item["line"] - 1
        section_end = len(source_lines)
        for later in source_headings[source_index + 1 :]:
            if later["level"] <= source_item["level"]:
                section_end = later["line"] - 1
                break
        source_section = "\n".join(source_lines[section_start:section_end])
        section_changed = replace_policy(source_section, target=doc.target) != source_section
        coverage.append(
            {
                "sourceHeading": source_item["heading"],
                "sourceLine": source_item["line"],
                "targetHeading": found["heading"],
                "targetSectionId": found["sectionId"],
                "targetLine": found["line"],
                "disposition": (
                    "SUPERSEDED_POLICY"
                    if source_index == 0
                    or source_item["heading"] != found["heading"]
                    or section_changed
                    else "PRESERVED"
                ),
            }
        )
    return target, coverage


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def build() -> dict[Path, bytes]:
    outputs: dict[Path, bytes] = {}
    coverage_documents: list[dict[str, Any]] = []
    manifest_documents: list[dict[str, Any]] = []
    for doc in DOCUMENTS:
        target_text, coverage = build_document(doc)
        target_bytes = target_text.encode()
        target_path = HERE / doc.target
        outputs[target_path] = target_bytes
        target_sections = headings(target_text)
        coverage_documents.append(
            {
                "logicalId": doc.logical_id,
                "sourcePath": doc.source.relative_to(ROOT).as_posix(),
                "targetPath": target_path.relative_to(ROOT).as_posix(),
                "sourceSha256": sha256(doc.source.read_bytes()),
                "targetSha256": sha256(target_bytes),
                "sourceHeadingCount": len(coverage),
                "mappedHeadingCount": len(coverage),
                "mappings": coverage,
            }
        )
        manifest_documents.append(
            {
                "logicalId": doc.logical_id,
                "path": target_path.relative_to(ROOT).as_posix(),
                "sha256": sha256(target_bytes),
                "authorityClass": doc.authority_class,
                "sections": [
                    {"sectionId": section["sectionId"], "heading": section["heading"], "level": section["level"]}
                    for section in target_sections
                ],
                "generationId": GENERATION_ID,
                "derivedFrom": doc.derived_from,
                "required": True,
            }
        )
    total_source_headings = sum(item["sourceHeadingCount"] for item in coverage_documents)
    total_mapped_headings = sum(item["mappedHeadingCount"] for item in coverage_documents)
    coverage_value: dict[str, Any] = {
        "schemaVersion": 1,
        "generationId": GENERATION_ID,
        "generatedAt": GENERATED_AT,
        "rule": "Every immutable V3 heading maps in source order to preserved or explicitly superseded V3.1-ZH content.",
        "documents": coverage_documents,
        "totals": {
            "sourceHeadingCount": total_source_headings,
            "mappedHeadingCount": total_mapped_headings,
        },
    }
    coverage_bytes = canonical_json(coverage_value)
    outputs[COVERAGE_PATH] = coverage_bytes
    manifest_value: dict[str, Any] = {
        "schemaVersion": 1,
        "generationId": GENERATION_ID,
        "generatedAt": GENERATED_AT,
        "authorityModel": {
            "operatingDoctrine": "ZERO_FOUNDER_INTERVENTION_AFTER_BOOTSTRAP",
            "humanApprovalRuntimeState": False,
            "externalTruthRequiresAttributableReceipts": True,
            "machineAuthorityIndependentOffRepository": True,
            "releaseFlow": "DIRECT_MAIN_EXACT_SHA_MACHINE_RECEIPT_POST_PUSH_VERIFY",
            "activationRequiresSignedExactShaReceipt": True,
            "b004": "CRITICAL_SCOPED_NONBLOCKING_EXTERNAL_WAIT",
        },
        "supersession": {
            "supersedesGenerationId": "traincapsule-v3-2026-08-11",
            "disposition": "ACTIVE_OPERATIONAL_AMENDMENT_WHEN_POINTER_SELECTED",
            "doesNotClaimExactV3Conformance": True,
            "preservesHistoricalGeneration": True,
            "rationale": "Replace runtime person-dependent approval with independent machine authority while preserving V3 product and truth laws.",
            "residualRisk": "Encoded machine policy may miss novel contextual ambiguity that qualified-person review could detect.",
        },
        "documents": manifest_documents,
        "coverageEvidence": {
            "path": COVERAGE_PATH.relative_to(ROOT).as_posix(),
            "sha256": sha256(coverage_bytes),
            "sourceHeadingCount": total_source_headings,
            "mappedHeadingCount": total_mapped_headings,
        },
        "integrity": {
            "algorithm": "sha256",
            "documentCount": len(manifest_documents),
            "manifestSelfIncluded": False,
            "generatorPath": Path(__file__).resolve().relative_to(ROOT).as_posix(),
        },
    }
    outputs[MANIFEST_PATH] = canonical_json(manifest_value)
    return outputs


def validate(outputs: dict[Path, bytes]) -> list[str]:
    errors: list[str] = []
    ids: set[str] = set()
    paths: set[Path] = set()
    manifest = json.loads(outputs[MANIFEST_PATH])
    for document in manifest["documents"]:
        path = ROOT / document["path"]
        if document["logicalId"] in ids:
            errors.append(f"duplicate logical ID: {document['logicalId']}")
        if path in paths:
            errors.append(f"duplicate path: {path}")
        ids.add(document["logicalId"])
        paths.add(path)
        if sha256(outputs[path]) != document["sha256"]:
            errors.append(f"internal digest mismatch: {path}")
        text = outputs[path].decode()
        body = text.split("## V3.1-ZH controlling amendment", 1)[-1]
        for pattern in (r"WAITING_HUMAN", r"HUMAN_REVIEWER", r"human approval", r"qualified human", r"human reviewer", r"human authority", r"founder/human"):
            if re.search(pattern, body, re.I):
                errors.append(f"forbidden active person-dependent clause {pattern!r}: {path}")
        for required in ("ZERO_FOUNDER_INTERVENTION_AFTER_BOOTSTRAP", "B004", "WAITING_EXTERNAL", "UNKNOWN"):
            if required not in text:
                errors.append(f"missing doctrine {required!r}: {path}")
        for label, pattern in FORBIDDEN_ACTIVE_SEMANTICS:
            if pattern.search(body):
                errors.append(f"forbidden active semantic ({label}): {path}")
        for required in REQUIRED_TARGET_DOCTRINE.get(path.name, ()):
            if required not in body:
                errors.append(f"missing target doctrine {required!r}: {path}")
    coverage = json.loads(outputs[COVERAGE_PATH])
    if coverage["totals"]["sourceHeadingCount"] != coverage["totals"]["mappedHeadingCount"]:
        errors.append("heading coverage is incomplete")
    if sha256(outputs[COVERAGE_PATH]) != manifest["coverageEvidence"]["sha256"]:
        errors.append("coverage digest mismatch")
    if len(manifest["documents"]) != 11:
        errors.append("manifest must contain exactly 11 normative documents")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    outputs = build()
    errors = validate(outputs)
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
        return 1
    if args.check:
        drift = [path for path, data in outputs.items() if not path.exists() or path.read_bytes() != data]
        if drift:
            print("ERROR: generated V3.1-ZH source drift: " + ", ".join(str(path) for path in drift), file=sys.stderr)
            return 1
    else:
        for path, data in outputs.items():
            path.write_bytes(data)
    manifest = json.loads(outputs[MANIFEST_PATH])
    print(
        f"PASS: {len(manifest['documents'])} V3.1-ZH documents, "
        f"{manifest['coverageEvidence']['mappedHeadingCount']} V3 headings mapped, hashes exact"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
