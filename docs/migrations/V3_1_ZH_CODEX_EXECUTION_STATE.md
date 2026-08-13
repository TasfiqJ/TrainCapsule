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

- Candidate commit: `550bee834bd63cae0c30f7f96b4732d049124fd1`.
- Candidate tree: `55d08d4296fb781edaa142820d16511fc38da9f4`.
- Commit subject: `Build` (exact deterministic repository snapshot implementation).
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
- `4ca86ff` — exact-head local/hosted acceptance and truthful evidence checkpoint.
- `b53b68d` — complete deterministic Python runtime distribution and deployment hardening.
- `550bee8` — exact Git-object repository snapshot and dirty-workspace-proof runtime builds.

## Candidate evidence completed so far

The following results are candidate-bound local implementation evidence. They are not final
activation authority and do not replace pending hosted, installed, or live acceptance.

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
- Complete local repository suite passed 959/959 and the deployment suite passed 36/36.
- The complete Python 3.12 runtime archive was built twice with identical archive and manifest
  digests, then relocated and exercised without repository-local Python or user site packages.
- The relocated runtime imported the full locked third-party dependency closure, all eight
  TrainCapsule packages, and launched the bundled Claude SDK helper.
- Runtime archive/extraction traversal, link, hardlink, tamper, inventory, ownership, bounded
  streaming, crash-replay, and rollback negative controls passed.
- Two exact-commit runtime rebuilds from an intentionally dirty workspace matched byte-for-byte:
  archive `4c3858eef668568a2c97dd95b41fcbc7aa1a9263f282fd9017f9f63d1c022393`
  and manifest `950435333f74d2e27d80ecef66c5dc386861f53fa2e96903343dd37bd82a6b52`.
- Two exact `550bee8` repository-snapshot dry runs matched byte-for-byte and passed complete
  inventory, loose-object identity, strict Git fsck, exact HEAD/tree, remote-free, hook-free,
  alternate-free, and clean-tree validation. The archive digest was
  `4b4f839205fd94f32ba4ef930e1cdcb6fc8298d5551176b3d426c5a880fcae2b` and the
  self-digested manifest file digest was
  `9887bc006a2a5bc55b27e99f7dabc1775a0386fa4048d0d2fcd90f62fc494ef7`.
- Source authority, exact 109-row roadmap/completion policy, exact 124-row legacy mapping,
  tracked inventory, 63 V3 schemas, 63 V3.1 schemas, 19 verifier schemas, Ruff, and strict
  Pyright all passed at the candidate.

All eight hosted PR workflows passed at the previous implementation checkpoint `b53b68d`.
The eight exact-head `550bee8` workflows were queued or running when this state was recorded;
their completion plus the independent installed/live acceptance below remain required.

## Current runtime and external state

Observed after `b53b68d` was pushed:

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

1. Exact-head local acceptance is green; the `550bee8` hosted workflows are still in progress.
2. The independent root-owned verifier/runtime deployment does not exist on this host.
3. The trusted GitHub App identity, exact ruleset, and signed live ruleset observation are absent.
4. V3.1 MIG-016 through MIG-020 independent receipts remain pending.
5. The exact installed candidate has not passed all 20 mandatory canaries.
6. No signed LIVE activation transaction exists for this candidate.
7. No ordered seven-event post-activation observer receipt exists.
8. Customer, market, GPU, paid-use, and other outside facts remain UNKNOWN or `WAITING_EXTERNAL`
   where the contract requires them.

## Next exact action

1. Monitor and repair all eight exact-head `550bee8` hosted workflows until green.
2. Assemble the exact production bundle from the proven deterministic runtime/snapshot plus externally
   provisioned authority inputs; stage and dry-run it before any privileged apply.
3. Install and independently attest the verifier/runtime/service bundle while retaining STOP.
4. Provision the GitHub App and exact main ruleset; capture a signed live observation.
5. Run all 20 live canaries; missing live mechanisms remain blocked rather than simulated.
6. Obtain the exact signed activation receipt and ordered seven-event observation.
7. Merge only the exact verified SHA through the automated PR-only path.

## Activation state

`STOPPED / NOT AUTHORIZED`

The controller must remain stopped until every applicable critical/high row, server rule,
independent receipt, negative control, live canary, and post-activation observation passes.
For any ambiguity: retain or restore STOP, preserve artifacts and journals, do not merge, and
compare against the safety ref. Never rewrite `main` or destroy preserved queue, checkpoint,
evidence, or user inputs.
