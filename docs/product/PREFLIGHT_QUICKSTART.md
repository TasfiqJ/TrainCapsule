# TrainCapsule local preflight quickstart

This experimental, customer-local preflight does not run training, compare executions, claim root
cause, transmit evidence, or depend on a person to approve a runtime action.

## Independent product installation

The product packages are separate distributions. The factory wheel contains only `tcfactory`.

```bash
uv build --offline --wheel packages/traincapsule-core
uv build --offline --wheel packages/traincapsule-ingest-pytorch
uv build --offline --wheel packages/traincapsule-qualify
uv build --offline --wheel packages/traincapsule-cli
```

Install those four wheels into an isolated Python 3.12 environment, then verify the installed
executable (not a source-tree import):

```bash
uv venv .venv-product --python 3.12
uv pip install --python .venv-product/bin/python \
  packages/traincapsule-core/dist/traincapsule_core-0.1.0-py3-none-any.whl \
  packages/traincapsule-ingest-pytorch/dist/traincapsule_ingest_pytorch-0.1.0-py3-none-any.whl \
  packages/traincapsule-qualify/dist/traincapsule_qualify-0.1.0-py3-none-any.whl \
  packages/traincapsule-cli/dist/traincapsule_cli-0.1.0-py3-none-any.whl
.venv-product/bin/traincapsule doctor --json
```

The product dependency graph contains neither `tcfactory` nor the Claude SDK.

## Identity

```bash
.venv-product/bin/traincapsule identity workload \
  examples/product/workload-identity-input.json \
  --output /tmp/traincapsule-quickstart/workload.json --json

.venv-product/bin/traincapsule identity environment \
  examples/product/environment-identity-input.json \
  --output /tmp/traincapsule-quickstart/baseline-environment.json --json
```

Create the candidate environment record the same way after changing only its explicit candidate
material. The identity input's `materializationRecipeDigest` must be the SHA-256 digest of the
corresponding local recipe file. Use the generated `workloadId` and the two generated
`environmentId` values below; placeholders are shown only to make the binding explicit.

Environment variables are accepted as explicit decision-relevant inputs. Secret-named variables,
embedded URL credentials, bearer/basic authorization values, private keys, and secret assignments
are redacted by the versioned `traincapsule-redaction-v1` policy before hashing. A caller-supplied
digest cannot override the computed digest. Workload and environment evidence policies derive
identity strength; it is not caller-authored. Customer-attested, unverified, or conflicting identity
can never produce
`APPROVE_WITHIN_ENVELOPE`.

## Evidence and native baseline

```bash
.venv-product/bin/traincapsule ingest pytorch-flight-recorder \
  examples/product/flight-recorder/real-format \
  --case-id CASE-QUICKSTART \
  --store /tmp/traincapsule-quickstart/evidence \
  --captured-at 2026-08-11T20:00:00Z \
  --workload-id 'sha256:<generated-workload-id>' \
  --baseline-environment-id 'sha256:<generated-baseline-environment-id>' \
  --candidate-environment-id 'sha256:<generated-candidate-environment-id>' \
  --baseline-recipe /customer-local/baseline.recipe \
  --candidate-recipe /customer-local/candidate.recipe \
  --output /tmp/traincapsule-quickstart/import.json --json

.venv-product/bin/traincapsule native-baseline /tmp/traincapsule-quickstart/import.json \
  --store /tmp/traincapsule-quickstart/evidence \
  --executed-at 2026-08-11T20:01:00Z \
  --elapsed-seconds 60 \
  --operator-effort-seconds 0 \
  --unresolved-question "Whether machine-verifiable evidence permits the change." \
  --output /tmp/traincapsule-quickstart/native.json \
  --human-output /tmp/traincapsule-quickstart/native.md --json
```

The importer hashes raw bytes before parsing, preserves raw digests and unknown fields, uses
no-follow bounded reads, and records missing/unknown evidence without inference. `native-baseline`
generates both a strict machine record and a readable report from importer output. Native
sufficiency is derived only after reopening raw artifacts from the case-local CAS and proving that
the source format/version, import digest, entries, unknowns, missing-rank record, and native
findings match those bytes. Both materialization recipes are stored as content-addressed,
identity-bound evidence and re-opened during preflight. The versioned lifecycle-disagreement
policy carries its
evidence references and provenance digest; the CLI has no caller-authored decision option, and
preflight independently recomputes the same raw-evidence result.

Only a directory containing supported JSON shapes is accepted. Archives are not extracted or
interpreted, so traversal links and archive-bomb payloads cannot enter this ingestion path.

## Bound preflight

```bash
.venv-product/bin/traincapsule preflight preflight-input.json \
  --store /tmp/traincapsule-quickstart/evidence --json
```

The strict input binds one incident case to workload and baseline/candidate environment identities,
case-local verified artifacts, a classified completeness report, the generated native baseline,
original/proposed economics. The engine itself derives versioned pack, local-access, privacy,
export, source-version, and economics verification records from those bound inputs; preflight JSON
cannot supply verdicts. Unknown or incomparable economics produce `UNKNOWN`, while a proposed cost
above the original returns `TECHNICALLY_POSSIBLE_BUT_UNECONOMIC`. Before making a
decision, the CLI reopens every referenced object from the case-local CAS with no-follow reads and
verifies its SHA-256 digest. Security-sensitive CAS and report writes pin every directory component
with no-follow directory descriptors and publish relative to those descriptors, so a concurrent
directory rename cannot redirect content between validation and publication. There is no
human-availability input or human runtime gate. An input that cannot be verified produces `UNKNOWN`;
a deterministic denial produces `POLICY_BLOCKED` or `OUTSIDE_SUPPORTED_ENVELOPE`.

The copied bundle documents a human-review compatibility outcome, but the owner-directed
zero-human runtime does not expose that value. Partially verified or customer-attested identity
returns deterministic `UNKNOWN`/`NO_DECISION`; it never creates an intervention request and never
self-asserts an approval.

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | command completed and wrote/returned a truth record |
| 2 | invalid CLI use or malformed input |
| 10 | unsupported evidence version or outside the supported envelope |
| 11 | required evidence is incomplete |
| 12 | identity mismatch |
| 13 | deterministic policy block |
| 20 | qualification passed or native workflow is sufficient |
| 21 | technical result failed or proposed experiment is uneconomic |
| 22 | unknown / no safe decision |
| 23 | invalid oracle |
| 24 | decision deadline expired |
| 30 | local storage/output failure |
| 40 | security-policy failure |

With `--json`, command-body and CLI-parser errors are deterministic JSON. Commands are local-only;
there is no SaaS or network path.

For the current initial pack, the source policy accepts the exact tested PyTorch `2.5.1` runtime.
Every real-format rank file must declare the same Flight Recorder format, PyTorch runtime, and world
size; conflicting declarations fail closed. Human native reports flatten and HTML-escape
user-derived multiline text so it cannot create forged Markdown sections or decision headings.
