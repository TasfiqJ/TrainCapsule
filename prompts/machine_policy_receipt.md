# V3 machine-policy receipt verifier

Verify one deterministic policy decision for the exact candidate SHA. Bind the task packet,
source/context manifests, immutable checkpoint generation, candidate manifest, gate artifacts,
owner-directive digest, and finite retry budget. Reject stale, mismatched, missing, agent-substituted,
or replayed inputs.

Do not invent external evidence, change owner directives, publish a Git ref, or upgrade UNKNOWN.
Return PASS only for an exact candidate-bound receipt; otherwise return BLOCKED_POLICY with a bounded
finding and reproducible evidence.
