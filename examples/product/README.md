# TrainCapsule product fixtures

These fixtures exercise the bounded V3 product spine without a network, SaaS account,
training runner, baseline/candidate runner, or reduction engine.

- `flight-recorder/supported/` is the supported PyTorch Flight Recorder `1.0` fixture.
- `flight-recorder/unsupported/` proves that an unknown version stops as
  `UNSUPPORTED_VERSION`; it is never guessed or silently upgraded.
- The product journey tests construct eligible, missing-evidence, native-sufficient,
  policy-blocked, unknown, expired, and malicious-path cases from these fixtures.

All timestamps and identities used by the fixtures are explicit. Customer evidence remains
under the caller-selected local evidence-store path.
