---
paths:
  - "tcfactory/**/*"
  - "config/**/*"
  - ".claude/**/*"
  - "factory/product_definition_of_done.yaml"
  - "factory/feature_ledger.yaml"
---
# Factory-control rules
- The controller, not an agent, owns risk tier, model routing, protected paths, value thresholds, hidden tests, Git promotion, and completion.
- Sessions are disposable; Git, checkpoints, handoffs, and machine artifacts are durable state.
- Never introduce an API-key fallback, bypassPermissions, force push, or unsandboxed execution.
- Changes to factory authority require explicit calibration and sabotage tests.
