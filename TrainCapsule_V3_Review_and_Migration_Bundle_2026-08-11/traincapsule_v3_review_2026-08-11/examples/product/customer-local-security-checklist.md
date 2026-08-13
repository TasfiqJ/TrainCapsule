# Customer-Local Pilot Security Checklist

## Product and data boundary

- [ ] Raw code, data, checkpoints, topology, and traces remain in the approved customer boundary.
- [ ] No telemetry egress occurs by default.
- [ ] Every permitted endpoint is documented and allowlisted.
- [ ] AI executor access is explicitly scoped and disclosed.
- [ ] Support export is opt-in and shows the exact exported artifact set.

## Evidence ingestion

- [ ] Archives have count, size, recursion, and decompression limits.
- [ ] Paths are canonicalized.
- [ ] Symlink and traversal attacks are rejected.
- [ ] Raw artifact digest is recorded before parsing.
- [ ] Parser version and warnings are retained.
- [ ] Cross-case mixing is prevented.

## Runner

- [ ] Least-privileged identity.
- [ ] Read-only source/input mounts where practical.
- [ ] Dedicated writable artifact directory.
- [ ] CPU, memory, disk, GPU, and wall-clock limits.
- [ ] Process-tree termination.
- [ ] Network deny or explicit allowlist.
- [ ] Environment identity verified immediately before execution.
- [ ] Artifacts hashed immediately after execution.
- [ ] Infrastructure errors cannot be reported as qualification failures.

## Secrets and logs

- [ ] Versioned deterministic redaction policy.
- [ ] No secrets in command arguments where avoidable.
- [ ] Logs have classification and retention.
- [ ] OAuth/API credentials remain outside repository and support bundle.
- [ ] Secret scanning passes.

## Trust and release

- [ ] Exact candidate SHA recorded.
- [ ] Identity, reduction, recovery, and qualification oracles valid.
- [ ] Applicability and expiry present.
- [ ] Required human approvals signed and current.
- [ ] Unsupported claims listed.
- [ ] Revocation/correction path documented.

## Supply chain

- [ ] Dependencies pinned.
- [ ] SBOM generated.
- [ ] Vulnerability scan reviewed.
- [ ] Installation artifact signed.
- [ ] Upgrade and rollback tested.
