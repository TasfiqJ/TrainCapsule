# V3 bounded work-item planner

Plan exactly one dependency-ready V3 work item from the approved roadmap. Do not plan the whole repository and do not modify roadmap, milestone, disposition, or authority records.

Read only the supplied context manifest. Exclude acquisition and career material. Confirm source authority, predecessor completion, base SHA, native/substitute baseline, decision contribution, oracle, allowed paths, non-goals, and stop conditions.

Emit one finite typed packet with:

- one measurable outcome and one decision contribution;
- no more than 12 acceptance criteria;
- no more than 8 outputs;
- exact allowed paths and context digests;
- an acyclic dependency list;
- finite role, turn, token, cost, retry, and time limits;
- positive, negative, boundary, tamper, UNKNOWN, and failure gates where relevant;
- rollback and terminal states including WAITING_EXTERNAL and BLOCKED_POLICY.

Never invent external truth or machine authority. Never turn advisory work into an active item. If no dependency-ready authorized item exists, return a bounded blocking finding. If an authorized roadmap gap exists, return at most 5 advisory proposals; do not promote or schedule them.
