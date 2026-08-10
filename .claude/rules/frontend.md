---
paths:
  - "apps/web/**/*.{ts,tsx,css}"
  - "packages/ui/**/*.{ts,tsx,css}"
---
# Frontend rules
- The UI is a release cockpit, not a generic observability dashboard.
- Every displayed status must trace to machine evidence and distinguish PASS, FAIL, UNKNOWN, SKIPPED, and BLOCKED.
- A five-minute deterministic demo must expose the failure, attribution, known-good resolution, and reproduction.
- Add Playwright coverage for critical workflows and accessibility checks for interactive controls.
