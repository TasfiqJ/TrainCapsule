# TrainCapsule local preflight quickstart

This quickstart exercises the experimental, customer-local preflight. It does not run a training
job, compare baseline/candidate executions, claim root cause, or transmit evidence to a service.

## 1. Install and verify

From the repository root:

```bash
uv sync --extra dev --frozen
uv run traincapsule doctor --json
```

`doctor` must report `networkRequired: false`.

## 2. Create the incident case

```bash
uv run traincapsule case init \
  --case-id CASE-QUICKSTART \
  --decision-owner incident-owner \
  --decision-type "candidate approval" \
  --decision-deadline 2026-08-12T20:00:00Z \
  --incident-summary "controlled collective timeout" \
  --pack-candidate ddp-hang-v1 \
  --privacy-policy LOCAL_ONLY \
  --output /tmp/traincapsule-quickstart/case.json \
  --json
```

Outputs are never overwritten implicitly. Choose a new local output directory when repeating the
journey.

## 3. Bind workload and environment identity

```bash
uv run traincapsule identity workload \
  examples/product/workload-identity-input.json \
  --output /tmp/traincapsule-quickstart/workload.json --json

uv run traincapsule identity environment \
  examples/product/environment-identity-input.json \
  --output /tmp/traincapsule-quickstart/environment.json --json
```

The example data identity is deliberately `CUSTOMER_ATTESTED`; that is weaker than a content or
manifest digest and must not be presented as fully bound evidence.

## 4. Import controlled Flight Recorder evidence

```bash
uv run traincapsule ingest pytorch-flight-recorder \
  examples/product/flight-recorder/supported \
  --case-id CASE-QUICKSTART \
  --store /tmp/traincapsule-quickstart/evidence-store \
  --captured-at 2026-08-11T20:00:00Z \
  --output /tmp/traincapsule-quickstart/import.json \
  --json
```

The importer accepts only supported fixture version `1.0`, hashes raw bytes before parsing, rejects
symlinks/non-files, keeps unknown fields and raw digests, and records native observations without
inventing a root cause. Raw evidence remains at a customer-selected local CAS URI.

## 5. Exercise native baseline and preflight

The native-baseline and preflight inputs are strict JSON records described by:

- `schemas/product/native-baseline.schema.json`
- `schemas/product/preflight-inputs.schema.json`

The fully wired controlled journey constructs those records from the prior outputs and validates
the result:

```bash
uv run pytest -q tests/product/test_install_to_preflight_journey.py
```

For direct CLI use:

```bash
uv run traincapsule native-baseline native-baseline-input.json --json
uv run traincapsule preflight preflight-input.json --json
```

Eligibility can be eligible, eligible with human review, need more evidence, native sufficient,
technically possible but uneconomic, outside the supported envelope, policy blocked, or unknown.
Unknown cost is allowed; no ROI is fabricated.

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | success |
| 2 | invalid or malformed input |
| 3 | unsupported evidence version |
| 4 | local policy blocked the operation |
| 5 | local storage or output failure |

All commands are offline-first and operate on local paths. `--json` produces deterministic,
machine-readable output or errors.
