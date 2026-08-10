---
paths:
  - "tests/**/*"
  - "scripts/gates/**/*"
---
# Test rules
- Do not weaken assertions, broaden equality, add retries, xfail, skip, or change expected output to match a broken candidate.
- Test the environment outcome, not a model's narrative.
- Keep clean controls, seeded defects, negative controls, and hidden tests distinct.
- Record deterministic seeds and exact commands.
