---
paths:
  - "packages/{domain,identity,evidence,incident_ir,trust,reducer,recovery,contracts,qualify,exchange}/**/*"
  - "backends/**/*"
  - "incident-packs/**/*"
  - "schemas/**/*"
  - "tests/{property,mutation,fault-injection,replay,qualification,security,e2e}/**/*"
---
# Trust-core rules
- Preserve raw evidence; normalization may not erase a defect.
- Expected semantics must come from a contract, canonical fixture, independent oracle, or legal metamorphic relation.
- Shared implementation lineage is not an independent vote.
- UNKNOWN, SKIPPED, UNATTRIBUTED, INVALID_ORACLE, INFRASTRUCTURE_ERROR, and EXTERNAL_VALIDATION_REQUIRED are never PASS.
- Real backend and workload claims require the real pinned code path, not a reimplementation or mock.
