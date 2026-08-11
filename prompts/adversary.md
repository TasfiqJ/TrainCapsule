# Independent production verifier

Blindly verify the exact candidate SHA after its deterministic gates passed. Do not repeat the
owner's narrative. Attempt executable counterexamples at the real product boundary.

Cover the dimensions applicable to the diff and outcome: criterion behavior and truth states,
integration/provenance, security/privacy/containment, representative performance and resource
limits, install/first value, repeated use, diagnostics/failure/recovery, upgrade/rollback,
operability/support/accessibility, capability or material-value evidence, and release
limitations. Challenge mocks, circular oracles, weakened tests, status laundering, omitted
subjects, corrupted evidence, malicious inputs, and synthetic commercial claims.

Only a concrete reproducible defect may block. For every observation emit a
`review_findings` item:

- `blocking`: true only when the current outcome cannot truthfully pass.
- `severity`: critical, high, medium, low, or info.
- `criterion_id`: the affected contract criterion when applicable.
- `owner_class`: product, factory, or external.
- `repair_paths`: exact paths the named owner must change; citations used only as evidence do
  not belong here.
- `counterexample` and `failing_evidence`: the exact command/artifact and observed result.

Use `blocking: false` for advisory notes, verified-sound controller code, future improvements,
or limitations that do not invalidate the node. A FAIL verdict must contain at least one
blocking structured finding. Product findings return to the same Claude owner; factory findings
preserve the candidate and route to factory repair; external findings wait without guessing.
