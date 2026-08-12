# TrainCapsule

TrainCapsule is an evidence-first system for investigating accelerated-workload incidents and
qualifying a proposed change against an explicit customer decision. This repository contains the
bounded V3 factory migration and the first customer-local product preflight vertical.

## Maturity and non-claims

The product is **experimental**. The repository does not establish commercial validation,
production readiness, customer adoption, superior performance, or an advantage over native
tooling. Native diagnostics are preserved and may be sufficient. Customer, GPU, market, and paid
engagement evidence remains external and deferred until it actually exists.

The implemented product scope ends at evidence import, identity, native-baseline capture,
completeness, and eligibility preflight. It does not include a baseline/candidate runner,
reduction engine, GPU qualification claim, or commercial pack release.

## Repository layout

- `packages/traincapsule-core/`: strict product models, canonical identity, and local evidence CAS.
- `packages/traincapsule-ingest-pytorch/`: bounded PyTorch Flight Recorder import adapter.
- `packages/traincapsule-qualify/`: completeness and eligibility decisions.
- `packages/traincapsule-cli/`: offline-first `traincapsule` commands.
- `tcfactory/`: the finite, lane-aware V3 product-building factory.
- `docs/source-of-truth/v3-2026-08-11/`: active V3 source authority and manifest.
- `docs/source-of-truth/final-2026-08-09/`: preserved historical authority.
- `docs/migrations/`: migration evidence, test matrix, and rollback procedure.

## Local setup and verification

```bash
uv sync --extra dev --frozen
scripts/gates/fast_quality.sh
uv run pytest -q tests/product
uv run python scripts/generate_product_schemas.py --check
```

The complete factory and product quality path is local and deterministic. The owner-directed
runtime is fully unattended and publishes only an exact verified candidate SHA to `main`; it never
creates or pushes a non-main branch and never depends on a pull request. Required hosted checks run
against that exact `main` SHA. A failed or incomplete hosted result is quarantined and reverted by a
normal follow-up commit, with finite recovery and a durable hard stop if recovery itself fails.

## Product preflight

```bash
uv run traincapsule doctor --json
uv run pytest -q tests/product/test_install_to_preflight_journey.py
```

The second command exercises the controlled local journey from case creation through workload and
environment identity, Flight Recorder import, native baseline, evidence completeness, and an
eligibility decision. See [the preflight quickstart](docs/product/PREFLIGHT_QUICKSTART.md) for the
individual CLI commands and exit-code contract.

## Factory runtime

The migrated factory remains deliberately stopped while this overhaul is being verified. The final
runtime contract is zero-human: no work item, milestone, release, recovery, or commercial path may
wait for or fabricate a human approval. Missing external facts block only their dependent scope,
remain `UNKNOWN` or `WAITING_EXTERNAL`, and do not stop unrelated lanes. A dashboard may display
status while the controller is stopped. Preserved V2/T002 state is historical and never resumes
automatically.

Source precedence is defined in `SOURCE_PRECEDENCE.md`. External or customer-dependent claims must
remain external/deferred unless backed by attributable, machine-verifiable external evidence. The
zero-human/main-only owner deviation is explicit; the copied V3 bundle remains byte-identical.
