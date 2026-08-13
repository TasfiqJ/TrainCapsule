# TrainCapsule V3.1-ZH Codex execution state

This is the durable continuation record for the full V3.1-ZH remediation. Read it with
`01_CODEX_MASTER_EXECUTION_PROMPT.md` and
`docs/migrations/V3_1_ZH_REMAINING_ACCEPTANCE.md` before every continuation.

## Immutable starting point

- Repository: `TasfiqJ/TrainCapsule`.
- Baseline `main`: `1ae79ba02c2b0cbec9b21ad3d2fc08d0afdbface`.
- Safety ref: `safety/traincapsule-pre-v3-1-zh-hardening-20260812T122011Z`.
- Working branch: `codex/traincapsule-v3-1-zh-hardening`.
- Draft PR: `https://github.com/TasfiqJ/TrainCapsule/pull/2`, targeting `main`.
- Preserved untracked-input archive:
  `/home/jasim/projects/traincapsule-preservation-20260812T122011Z.tar.gz`.
- Preservation archive SHA-256:
  `037398dc1f42e8f9f79bb3d8e74ca6f05a05204957402a445cd0241ebfca8381`.
- Original V3.1-ZH ZIP SHA-256:
  `8780393305926d04697b78c615645bd908075708b61607c61571a76807551a64`.
- Pasted and packaged master-prompt SHA-256:
  `32ab80745d20e4e4b7fa30c948469a79d0cd9a6800d07bdbda0c9e43394351ed`.

The safety ref and branch were pushed before implementation changes. Direct pushes to
`main`, force pushes, test weakening, acceptance weakening, and fabricated evidence are
prohibited.

## Package processing and authority

- `00_START_HERE.md` was read first.
- All 43 payloads declared by `12_SHA256SUMS.txt` were verified byte-for-byte.
- All 44 package files, including the checksum ledger, were processed.
- The authority order is: master execution prompt; acceptance contract; zero-human audit;
  158-row matrix; historical sources; repository evidence.
- V3.1-ZH supersedes the historical owner-directed direct-main deviation. Active release
  authority is automated PR-only with independent machine authorization and no human approval.

Historical Phase-0 evidence is immutable. Its counts and SHA fields must never be presented
as current acceptance. Candidate reclassification is stored separately in
`docs/migrations/V3_1_ZH_158_ROW_FINDINGS_LEDGER.json`.

## Current implementation candidate

- Candidate commit: `81e46ce5ad95c588c8fae3bd64f5704e40ac984b`.
- Candidate tree: `b01b982b5a32926e00656c9ea8b1980c0d91e405`.
- Commit subject: `fix: bind commercial authority and portable migration evidence`.
- Branch push: complete.
- PR state: draft; merge is not authorized.

Relevant branch history:

- `1f05faa` — Phase-0 baseline and safety evidence.
- `75aaebd` — coherent V3.1-ZH authority.
- `b58a010` — strict V3.1 contracts.
- `665b4fb` — independent machine verifier.
- `7463302` — controlled source acquisition.
- `4a97eee` — native and decision-value gates.
- `5245425` — attributable market artifacts.
- `9092ec8` — preserved zero-human hardening work in progress.
- `bee1907` — immutable remediation inputs.
- `3907d65` — automatic refresh and evidence hardening.
- `16e65dc` — activation replay and clean evidence.
- `81e46ce` — commercial/reduction authority, portable legacy evidence, and hosted-runtime fixes.

## Candidate evidence completed so far

The following results are scoped implementation evidence. They are not final activation
authority and do not replace the pending complete local/hosted/live runs.

- Exact 109-row completion-evidence policy passed.
- Exact 63 V3 schema generation passed.
- Repository-wide Ruff passed.
- Repository-wide strict Pyright reported 0 errors and 0 warnings.
- 71 completion, market, milestone, activation, and external-action tests passed.
- Full controller simulation passed 28/28.
- Exact V2 legacy migration passed for all 124 entries.
- Legacy hostile suite passed 11/11.
- Runtime-path and supervisor hosted-regression suite passed 11/11.
- A clean checkout without ignored `factory/artifacts/T001` and `T002` runtime trees passed
  the relevant source and legacy workflow; optional local bytes remain exact-verified when present.
- Commercial maturity now requires a canonical receipt-backed stable product lineage across
  customer, offer, family, pack, candidate, and source generation.
- Reduction authority is loaded only from the signed installed-runtime authority and verified
  public machine-policy/LIVE activation receipts; launcher environment cannot select the oracle/key.
- Cross-identity, stale, revoked, rollback, missing-install, and substituted-install hostile
  controls fail closed.

Still required for this exact candidate: canonical full pre-evidence quality, all packaging
and clean-install checks, the complete local suite, and every exact-head hosted PR check.

## Current runtime and external state

Observed after `81e46ce` was pushed:

- Authoritative stop marker: `factory/state/STOP` is present.
- `factory/state/PAUSE` and `factory/state/HARD_STUCK` are absent.
- Product controller: stopped.
- Windows Automatic Activation: disabled.
- Windows Calibration Recovery: disabled.
- Windows Lights-Out Autopilot: disabled.
- Windows GitHub Runner task: ready; WSL `Runner.Listener` is running as the isolated CI runner.
- `/var/lib/traincapsule-verifier`: absent.
- `/var/lib/traincapsule-runtime`: absent.
- `/etc/traincapsule-verifier`: absent.
- `/etc/traincapsule-controller`: absent.
- `/opt/traincapsule-runtime`: absent.
- Machine-policy GitHub App ID: unprovisioned.
- Signed live ruleset observation: absent.
- Signed LIVE activation receipt: absent.
- Exact installed 20-canary result: absent.
- Seven-event post-activation observation: absent.

The GitHub runner is not an activation authority and does not permit controller startup.

## Candidate findings state

All 158 rows have been rebound to the implementation candidate without claiming final closure:

- 100 local implementations pending integrated local, hosted, installed, or live acceptance.
- 14 trusted external facts pending.
- 10 independent server/provisioning requirements pending.
- 32 exact live-canary/observer requirements pending.
- 2 V3.1 M0 external evidence requirements pending.
- 0 rows classified `PROVEN_FINAL`.

Exact membership and the immutable Phase-0 snapshot are stored in the machine-readable ledger.
The human no-forgetting sequence is in `V3_1_ZH_REMAINING_ACCEPTANCE.md`.

## Blockers that prohibit activation

1. Complete candidate-bound local and hosted acceptance has not finished.
2. The independent root-owned verifier/runtime deployment does not exist on this host.
3. The trusted GitHub App identity, exact ruleset, and signed live ruleset observation are absent.
4. V3.1 MIG-016 through MIG-020 independent receipts remain pending.
5. The exact installed candidate has not passed all 20 mandatory canaries.
6. No signed LIVE activation transaction exists for this candidate.
7. No ordered seven-event post-activation observer receipt exists.
8. Customer, market, GPU, paid-use, and other outside facts remain UNKNOWN or `WAITING_EXTERNAL`
   where the contract requires them.

## Next exact action

1. Commit the candidate-bound inventory, ledger, and truthful durable documentation.
2. Run the canonical complete local/pre-evidence acceptance against that exact head.
3. Push the evidence checkpoint and repair all hosted PR checks until exact-head green.
4. Stage, dry-run, install, and independently attest the verifier/runtime/service bundle.
5. Provision the GitHub App and exact main ruleset; capture a signed live observation.
6. Run all 20 live canaries; missing live mechanisms remain blocked rather than simulated.
7. Obtain the exact signed activation receipt and ordered seven-event observation.
8. Merge only the exact verified SHA through the automated PR-only path.

## Activation state

`STOPPED / NOT AUTHORIZED`

The controller must remain stopped until every applicable critical/high row, server rule,
independent receipt, negative control, live canary, and post-activation observation passes.
For any ambiguity: retain or restore STOP, preserve artifacts and journals, do not merge, and
compare against the safety ref. Never rewrite `main` or destroy preserved queue, checkpoint,
evidence, or user inputs.
