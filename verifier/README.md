# TrainCapsule independent verifier

This distribution is a separate V3.1-ZH policy implementation. It imports no `tcfactory`
code and must be installed outside the candidate/controller account's write authority.

Repository content is public reference/client/schema/install-rehearsal code only. Production
policy, private oracles/fixtures, signing keys, revocation state, GitHub credential, receipts,
and logs belong outside the repository:

```text
/etc/traincapsule-verifier/
/var/lib/traincapsule-verifier/
/var/lib/traincapsule-verifier/private/
/var/lib/traincapsule-verifier/oracle/
/var/log/traincapsule-verifier/
```

The repository does not contain a signing key, private policy/oracle, credential, or fabricated
receipt. `rehearse-install` creates a disposable `STAGED_NOT_ACTIVATED` layout only. It never
touches `/etc`, `/var`, GitHub, Git, or the TrainCapsule runtime.

The verifier keeps directory descriptors open after ownership validation, rejects writable or
non-regular trust files, and performs reads and publications relative to those descriptors. It
recomputes request identity; checks exact work-item, milestone, lane, candidate, tree, source,
context, packet, manifest, and checkpoint bindings; and rejects non-normalized scopes. Approved
root-owned oracle executables are content-addressed by policy, run in a separate process, and
their strict output must exactly match the trusted manifest. Each nonce is consumed once.

Revocation state must match a separately provisioned authority anchor containing the exact key,
key epoch, predecessor-key-anchor digest, revocation epoch, current-list digest, and previous-list
digest. A policy/list/key rollback therefore cannot be accepted against the current anchor. Only
a verified, current, unrevoked local receipt can
authorize the exact check name `TrainCapsule / Machine policy`.

Activation reopens trusted machine-environment, controller-binary, and controller-configuration
artifacts and recomputes their digests before issue and verification. Verification also rechecks
the exact linked policy receipt against current revocation state and enforces future-time and
one-hour lifetime bounds. This repository implementation alone does not activate anything.

Installation attestation parses and cross-checks policy, public/private keys, revocations,
authority anchor, and approved oracle files when present. It remains
`STAGED_NOT_ACTIVATED` until a separate live oracle and service authority is actually verified;
file presence alone can never produce `READY`.
