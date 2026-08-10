---
name: traincapsule-contract
description: Apply TrainCapsule authority, truth-state, faithfulness, applicability, and evidence-exchange rules.
---

# TrainCapsule contract discipline

1. Use the protected authority order and cite exact source sections.
2. Never treat correlated implementations, model assertions, or candidate-derived answers as independent evidence.
3. Preserve raw evidence, provenance, actor/rank identity, topology, timing uncertainty, data/checkpoint state, and collection loss.
4. Reduction must preserve the declared incident and causal class. When faithfulness cannot be shown, return UNKNOWN or INVALID_ORACLE.
5. PASS, FAIL, UNKNOWN, INVALID_ORACLE, INFRASTRUCTURE_ERROR, and EXTERNAL_VALIDATION_REQUIRED remain distinct.
6. A real backend, workload, recovery, or qualification claim must execute the pinned path. Mocks and scale emulation are labelled controls only.
7. A qualification contract must be applicable, current, unrevoked, and inside its declared envelope.
8. Close and Qualify results must expose what was attempted, what was unavailable, and what evidence was lost.
9. Exchange artifacts must be sanitized, policy-allowed, attributable, integrity-protected, and explicit about export tier.
10. State exactly what the evidence proves and does not prove.
