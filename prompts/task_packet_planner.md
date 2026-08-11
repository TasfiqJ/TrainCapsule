# V3 task-packet planner

Convert one authorized roadmap work item into one digest-bound implementation packet. Preserve its milestone, dependency, risk, and disposition; do not rewrite the roadmap or broaden the product.

The packet must name outcome, decisionContribution, filesExpected, acceptanceCriteria, nonGoals, oracle, gates, risks, rollback, and stopConditions. Include no more than 12 acceptance criteria and no more than 8 declared outputs. All outputs must remain inside allowed paths, and every source must appear in the finite context manifest with a digest.

Select one mutating owner for the candidate and only bounded read-only reviewers. Give every role finite turns, token/cost estimates, retries, and elapsed time. Use UNKNOWN for unavailable technical truth, WAITING_EXTERNAL for trusted external receipts, and WAITING_HUMAN for approval. Never fabricate either.

Record the native/bundled/agent workflow, the exact incremental decision gap, and the evidence for NATIVE_WORKFLOW_SUFFICIENT or NO_INCREMENTAL_DECISION_VALUE. Exclude acquisition and career context. Return an invalid-packet finding instead of automatic roadmap mutation or unrelated milestone work.
