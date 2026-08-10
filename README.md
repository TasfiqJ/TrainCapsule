# TrainCapsule

TrainCapsule is an evidence system for accelerated-workload failure reproduction and change qualification.

Its product workflow is organized into three loops:

- **Close:** capture, reduce, replay, localize, and verify a failure or recovery.
- **Qualify:** test a proposed stack, policy, hardware, data, or recovery change against explicit contracts.
- **Exchange:** package attributable, policy-controlled evidence for internal teams and authorized vendors.

This repository is in factory bootstrap state. The protected source-of-truth bundle is installed under `docs/source-of-truth/final-2026-08-09/`. Product implementation must not start until authentication, role separation, private gates, calibration, recovery controls, and private release routing have passed.

The initial contract packs are:

- `PRE_COLLECTIVE_LIFECYCLE_CONTRACT_V1`
- `CHECKPOINT_RESUME_STATE_CONSISTENCY_V1`

External or customer-dependent claims remain `EXTERNAL_VALIDATION_REQUIRED` until supported by attributable evidence.
