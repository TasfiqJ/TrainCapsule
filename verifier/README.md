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

## Public verification boundary

Install the `traincapsule-verifier-verify-receipt` console script as the exact regular file
`/usr/local/bin/traincapsule-verifier-verify-receipt`, owned by root and not writable by the
controller account, its group, or other users. The script exposes only `verify-receipt` and
`verify-activation`. It has no flags for changing trust roots and no import of the signing-key
or issuing implementation. It reads only these public roots:

```text
/etc/traincapsule-verifier/policy.json
/etc/traincapsule-verifier/public-key.pem
/var/lib/traincapsule-verifier/revocations.json
/var/lib/traincapsule-verifier/authority-anchor.json
/var/lib/traincapsule-verifier/receipts/*.json
```

All roots and files must be root-owned, outside the candidate repository, and non-writable by
group or other. The executable and its parent must also be root-owned and non-writable. The
client pins its executable inode while it verifies and rechecks it before emitting one strict
authorization JSON object. Service absence, malformed state, stale or revoked authority, a
non-local receipt, a changed executable, or any argument mismatch returns nonzero and emits no
authorization.

There is deliberately no receipt-issuing CLI in the public client. Production bootstrap must
create a separate verifier service account, install private signing material as mode `0600`
under a service-only root, install signed policy/revocation/anchor state through a privileged
operator, and make the controller unable to execute the issuer service or read its private
root. Until those ownership and service-manager controls are installed and independently
attested, issuance and activation remain unavailable.

The staged production layout resolves receipt ownership through two distinct locations:

```text
/var/lib/traincapsule-verifier/outbox/   traincapsule-verifier:traincapsule-verifier 0700
/var/lib/traincapsule-verifier/receipts/ root:root                                  0755
```

The service-only issuer can write the private outbox but cannot write public receipts. A minimal
root broker accepts one receipt filename, opens the outbox and public roots by directory
descriptor without following links, re-parses canonical JSON, independently verifies the signed
receipt against current root-owned policy/key/revocation/anchor state, requires the signed receipt
ID to equal the filename, and promotes exact bytes with exclusive-create semantics. An identical
existing public receipt is an idempotent replay; different bytes at the same identity are rejected.
The controller cannot read the private key/oracle/outbox or execute the issuer. No generic issuing
command is exposed to the controller.

`traincapsule-verifier-plan-install` prints an inert `STAGED_NOT_ACTIVATED` install manifest, or
with `--stage` writes only into an absent or empty caller-selected staging directory. The manifest
contains exact owners/modes, negative access assertions, content digests for service-manager
units, and an ordered rollback plan. It never creates users, writes `/etc` or `/var`, enables a
service, installs credentials, calls GitHub, or asserts live readiness.

## GitHub App check worker boundary

`check_publisher.py` defines the network-free polling and publication protocol for a separately
credentialed GitHub App adapter. The installed worker policy pins the repository, GitHub App ID,
installation, backend identity, credential reference, and exact check name. Each candidate/check/receipt
action is reserved with an exclusive durable claim before a side effect; its delivery receipt
must bind the same action digest, backend, repository, installation, candidate SHA, conclusion,
and receipt. After an ambiguous failure the worker performs lookup/reconciliation only and will
not send a second create request. An unavailable event becomes `WAITING_EXTERNAL_CHANNEL` while
the polling loop continues processing other events.

The repository provides no GitHub transport, token, App private key, webhook, public server, or
live installation. A production adapter must authenticate as an independently owned GitHub App,
poll an allowlisted repository/installation, implement durable lookup by `actionDigest`, and
guarantee `publish` is idempotent for that digest before it can be connected to the worker.
