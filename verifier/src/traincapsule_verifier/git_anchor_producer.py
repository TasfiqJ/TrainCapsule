"""Independent GitHub-App producer and root promoter for exact-main anchor imports."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import pwd
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, cast

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from pydantic import Field, model_validator

from .canonical import canonical_json_bytes, model_digest, sha256_digest
from .crypto import load_private_key, sign_model
from .filesystem import open_trusted_root, read_bounded_file
from .git_anchor_updater import AnchorUpdateRequest, valid_main_parent_binding
from .models import ObservedMainReceipt, RulesetObservationReceipt, SourceGenerationId, V31Model
from .public_crypto import load_public_key, verify_model_signature

FETCHER_USER = "traincapsule-anchor-fetcher"
CONTROLLER_USER = "traincapsule-controller"
ROOT = Path("/var/lib/traincapsule-verifier")
CONFIG = Path("/etc/traincapsule-verifier")
CONTROLLER_TRANSACTIONS = Path("/var/lib/traincapsule-runtime/publication-transactions")
FETCHER_INBOX = ROOT / "anchor-fetcher-inbox"
FETCHER_OUTBOX = ROOT / "anchor-fetcher-outbox"
UPDATER_INBOX = ROOT / "anchor-updates"


class AnchorFetchJob(V31Model):
    schema_version: Literal["3.1"] = "3.1"
    job_id: str = Field(pattern=r"^ANCHORJOB:[A-Z0-9:_-]{8,120}$")
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    base_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    merged_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    publication_transaction_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_generation_id: SourceGenerationId
    source_generation_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    created_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def bounded(self) -> AnchorFetchJob:
        lifetime = self.expires_at.astimezone(UTC) - self.created_at.astimezone(UTC)
        if self.base_sha == self.merged_main_sha or not 0 < lifetime.total_seconds() <= 1800:
            raise ValueError("anchor fetch job is not a bounded main advancement")
        return self


class AnchorProducerPolicy(V31Model):
    schema_version: Literal["3.1"] = "3.1"
    repository: Literal["TasfiqJ/TrainCapsule"]
    github_app_id: int = Field(gt=0)
    installation_id: int = Field(gt=0)
    permissions: dict[str, Literal["read"]]
    required_check_app_ids: dict[str, int] = Field(min_length=1)
    source_generation_id: SourceGenerationId
    source_generation_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    private_key_path: Literal[
        "/var/lib/traincapsule-verifier/anchor-fetcher-private/github-app-private-key.pem"
    ]
    observer_key_path: Literal[
        "/var/lib/traincapsule-verifier/anchor-fetcher-private/observer-private-key.pem"
    ]
    ruleset_receipt_path: Literal["/var/lib/traincapsule-verifier/ruleset/current.json"]
    ruleset_public_key_path: Literal["/etc/traincapsule-verifier/ruleset-public-key.pem"]

    @model_validator(mode="after")
    def least_privilege(self) -> AnchorProducerPolicy:
        if self.permissions != {
            "checks": "read",
            "contents": "read",
            "pull_requests": "read",
        }:
            raise ValueError("anchor fetcher GitHub App permissions are not exact read-only scope")
        return self


def _trusted_raw(path: Path, *, uid: int, mode: int, maximum: int) -> bytes:
    observed = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(observed.st_mode)
        or observed.st_uid != uid
        or stat.S_IMODE(observed.st_mode) != mode
        or observed.st_nlink != 1
        or not 0 < observed.st_size <= maximum
    ):
        raise ValueError("anchor producer input identity is untrusted")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            observed.st_dev,
            observed.st_ino,
            observed.st_size,
        ):
            raise ValueError("anchor producer input changed before read")
        raw = os.read(descriptor, maximum + 1)
        if len(raw) != observed.st_size:
            raise ValueError("anchor producer input changed during read")
        return raw
    finally:
        os.close(descriptor)


def _atomic(path: Path, raw: bytes, *, uid: int, gid: int, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
    try:
        os.write(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chown(temporary, uid, gid, follow_symlinks=False)
    os.replace(temporary, path)


def _canonical_mapping(raw: bytes) -> dict[str, object]:
    try:
        value: object = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("publication transaction is invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("publication transaction is not an object")
    typed = cast(dict[str, object], value)
    if canonical_json_bytes(typed) != raw:
        raise ValueError("publication transaction is not canonical")
    return typed


def stage_jobs(
    policy: AnchorProducerPolicy,
    *,
    transaction_root: Path = CONTROLLER_TRANSACTIONS,
    inbox: Path = FETCHER_INBOX,
    now: datetime | None = None,
) -> list[Path]:
    """Root-only narrow broker from controller transactions to the fetcher inbox."""

    if os.geteuid() != 0:
        raise ValueError("anchor job broker requires root")
    controller = pwd.getpwnam(CONTROLLER_USER)
    fetcher = pwd.getpwnam(FETCHER_USER)
    current = (now or datetime.now(UTC)).astimezone(UTC)
    staged: list[Path] = []
    for transaction_path in sorted(transaction_root.glob("*.json")):
        raw = _trusted_raw(transaction_path, uid=controller.pw_uid, mode=0o600, maximum=2_000_000)
        try:
            transaction: object = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("publication transaction is invalid") from exc
        if not isinstance(transaction, dict):
            raise ValueError("publication transaction is not an object")
        typed = cast(dict[str, object], transaction)
        if typed.get("phase") != "MERGED":
            continue
        base = typed.get("baseSha")
        merged = typed.get("mergedMainSha")
        tx_id = typed.get("transactionId")
        updated_at = typed.get("updatedAt")
        try:
            transaction_time = datetime.fromisoformat(
                str(updated_at).replace("Z", "+00:00")
            ).astimezone(UTC)
        except ValueError as exc:
            raise ValueError("merged publication transaction timestamp is invalid") from exc
        if not all(isinstance(value, str) for value in (base, merged, tx_id)):
            raise ValueError("merged publication transaction is incomplete")
        canonical_transaction = canonical_json_bytes(typed)
        job = AnchorFetchJob(
            job_id=f"ANCHORJOB:{cast(str, tx_id)}",
            repository=policy.repository,
            base_sha=cast(str, base),
            merged_main_sha=cast(str, merged),
            publication_transaction_digest=sha256_digest(canonical_transaction),
            source_generation_id=policy.source_generation_id,
            source_generation_digest=policy.source_generation_digest,
            created_at=transaction_time,
            expires_at=transaction_time + timedelta(minutes=30),
        )
        stem = job.job_id.replace(":", "_")
        job_path = inbox / f"{stem}.job.json"
        transaction_target = inbox / f"{stem}.publication.json"
        if job_path.exists():
            if (
                job_path.read_bytes() != canonical_json_bytes(job)
                or not transaction_target.is_file()
                or transaction_target.read_bytes() != canonical_transaction
            ):
                raise ValueError("anchor fetch job replay conflicts")
            continue
        if job.expires_at <= current:
            continue
        _atomic(
            transaction_target,
            canonical_transaction,
            uid=fetcher.pw_uid,
            gid=fetcher.pw_gid,
        )
        _atomic(
            job_path,
            canonical_json_bytes(job),
            uid=fetcher.pw_uid,
            gid=fetcher.pw_gid,
        )
        staged.append(job_path)
    return staged


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _app_token(policy: AnchorProducerPolicy, key_raw: bytes) -> str:
    key = serialization.load_pem_private_key(key_raw, password=None)
    if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
        raise ValueError("anchor fetcher GitHub App key is invalid")
    now = int(time.time())
    header = _b64url(b'{"alg":"RS256","typ":"JWT"}')
    payload = _b64url(
        json.dumps(
            {"iat": now - 30, "exp": now + 540, "iss": policy.github_app_id},
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )
    unsigned = f"{header}.{payload}".encode()
    jwt = f"{header}.{payload}.{_b64url(key.sign(unsigned, padding.PKCS1v15(), hashes.SHA256()))}"
    request = urllib.request.Request(
        f"https://api.github.com/app/installations/{policy.installation_id}/access_tokens",
        data=canonical_json_bytes(
            {
                "permissions": policy.permissions,
                "repositories": [policy.repository.split("/", 1)[1]],
            }
        ),
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {jwt}",
            "Content-Type": "application/json",
            "User-Agent": "TrainCapsule-Anchor-Fetcher/3.1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload_raw: object = json.loads(response.read(1_000_000))
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise ValueError("anchor fetcher installation token is unavailable") from exc
    if not isinstance(payload_raw, dict):
        raise ValueError("anchor fetcher installation token response is invalid")
    typed_payload = cast(dict[str, object], payload_raw)
    if not isinstance(typed_payload.get("token"), str):
        raise ValueError("anchor fetcher installation token response is invalid")
    return cast(str, typed_payload["token"])


def _github_json(path: str, token: str) -> object:
    request = urllib.request.Request(
        "https://api.github.com" + path,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "TrainCapsule-Anchor-Fetcher/3.1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read(4_000_000))
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise ValueError("anchor fetcher GitHub observation is unavailable") from exc


def _run_git(arguments: list[str], *, cwd: Path, token: str | None = None) -> str:
    environment = {
        "PATH": "/usr/bin:/bin",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    if token is not None:
        environment.update(
            {
                "GIT_ASKPASS": "/usr/libexec/traincapsule-anchor-askpass",
                "GIT_TERMINAL_PROMPT": "0",
                "TRAINCAPSULE_GITHUB_PASSWORD": token,
            }
        )
    result = subprocess.run(
        ["/usr/bin/git", *arguments],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
        env=environment,
    )
    if result.returncode != 0:
        raise ValueError("anchor fetcher Git operation failed")
    return result.stdout.strip()


def _verified_checks(raw: object, policy: AnchorProducerPolicy) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise ValueError("anchor fetcher check response is invalid")
    typed_raw = cast(dict[str, object], raw)
    if not isinstance(typed_raw.get("check_runs"), list):
        raise ValueError("anchor fetcher check response is invalid")
    found: dict[str, str] = {}
    for item_raw in cast(list[object], typed_raw["check_runs"]):
        if not isinstance(item_raw, dict):
            continue
        item = cast(dict[str, object], item_raw)
        app = item.get("app")
        app_id = cast(dict[str, object], app).get("id") if isinstance(app, dict) else None
        name = item.get("name")
        if (
            isinstance(name, str)
            and item.get("status") == "completed"
            and item.get("conclusion") == "success"
            and app_id == policy.required_check_app_ids.get(name)
        ):
            key = "CHECK:" + hashlib.sha256(name.encode()).hexdigest()[:24].upper()
            found[key] = sha256_digest(canonical_json_bytes(item))
    if len(found) != len(policy.required_check_app_ids):
        raise ValueError("anchor fetcher required checks are missing or spoofed")
    return found


def produce(
    policy: AnchorProducerPolicy,
    *,
    inbox: Path = FETCHER_INBOX,
    outbox: Path = FETCHER_OUTBOX,
    token_factory: Callable[[AnchorProducerPolicy, bytes], str] = _app_token,
    now: datetime | None = None,
) -> list[Path]:
    """Fetch exact main through a read-only GitHub App and emit unsigned import material."""

    fetcher = pwd.getpwnam(FETCHER_USER)
    if os.geteuid() != fetcher.pw_uid:
        raise ValueError("anchor producer requires its dedicated service identity")
    key_raw = _trusted_raw(
        Path(policy.private_key_path), uid=fetcher.pw_uid, mode=0o600, maximum=64_000
    )
    observer_key_raw = _trusted_raw(
        Path(policy.observer_key_path), uid=fetcher.pw_uid, mode=0o600, maximum=64_000
    )
    ruleset_raw = _trusted_raw(
        Path(policy.ruleset_receipt_path), uid=0, mode=0o444, maximum=1_000_000
    )
    ruleset_key_raw = _trusted_raw(
        Path(policy.ruleset_public_key_path), uid=0, mode=0o444, maximum=16_000
    )
    ruleset = RulesetObservationReceipt.model_validate_json(ruleset_raw, strict=True)
    verify_model_signature(ruleset, load_public_key(ruleset_key_raw))
    token = token_factory(policy, key_raw)
    produced: list[Path] = []
    for job_path in sorted(inbox.glob("ANCHORJOB_*.job.json")):
        job_raw = _trusted_raw(job_path, uid=fetcher.pw_uid, mode=0o600, maximum=64_000)
        job = AnchorFetchJob.model_validate_json(job_raw, strict=True)
        stem = job_path.name.removesuffix(".job.json")
        publication_raw = _trusted_raw(
            inbox / f"{stem}.publication.json",
            uid=fetcher.pw_uid,
            mode=0o600,
            maximum=2_000_000,
        )
        ready = outbox / f"{stem}.ready"
        if ready.is_dir():
            existing = [
                ready / suffix
                for suffix in (
                    "observed.json",
                    "ruleset.json",
                    "publication.json",
                    "bundle",
                    "request.json",
                )
            ]
            if not all(path.is_file() for path in existing):
                raise ValueError("anchor producer committed output is incomplete")
            produced.extend(existing)
            continue
        observed_now = (now or datetime.now(UTC)).astimezone(UTC)
        if (
            canonical_json_bytes(job) != job_raw
            or job.repository != policy.repository
            or job.source_generation_id != policy.source_generation_id
            or job.source_generation_digest != policy.source_generation_digest
            or job.publication_transaction_digest != sha256_digest(publication_raw)
        ):
            raise ValueError("anchor fetch job or authority binding is invalid")
        if job.expires_at <= observed_now:
            continue
        if (
            ruleset.repository != job.repository
            or ruleset.expires_at <= observed_now
        ):
            raise ValueError("anchor authority binding is invalid")
        transaction = _canonical_mapping(publication_raw)
        candidate_sha = transaction.get("candidateSha")
        if (
            not isinstance(candidate_sha, str)
            or candidate_sha != job.merged_main_sha
            or transaction.get("baseSha") != job.base_sha
        ):
            raise ValueError("anchor fetcher direct-main publication binding is invalid")
        branch = _github_json(f"/repos/{job.repository}/branches/main", token)
        if not isinstance(branch, dict):
            raise ValueError("anchor fetcher main response is invalid")
        commit_summary = cast(dict[str, object], branch).get("commit")
        remote_sha = (
            cast(dict[str, object], commit_summary).get("sha")
            if isinstance(commit_summary, dict)
            else None
        )
        if remote_sha != job.merged_main_sha:
            continue
        checks = _verified_checks(
            _github_json(
                f"/repos/{job.repository}/commits/{job.merged_main_sha}/check-runs",
                token,
            ),
            policy,
        )
        with tempfile.TemporaryDirectory(prefix="anchor-fetch-") as raw:
            stage = Path(raw) / "stage.git"
            stage.mkdir(mode=0o700)
            _run_git(["init", "--bare", str(stage)], cwd=Path(raw))
            _run_git(
                [
                    "-C",
                    str(stage),
                    "fetch",
                    "--no-tags",
                    "https://github.com/" + job.repository + ".git",
                    "+refs/heads/main:refs/heads/main",
                ],
                cwd=Path(raw),
                token=token,
            )
            main = _run_git(
                ["-C", str(stage), "rev-parse", "refs/heads/main"], cwd=Path(raw)
            )
            tree = _run_git(
                ["-C", str(stage), "rev-parse", f"{main}^{{tree}}"], cwd=Path(raw)
            )
            parents = _run_git(
                ["-C", str(stage), "show", "-s", "--format=%P", main],
                cwd=Path(raw),
            ).split()
            if main != job.merged_main_sha or not valid_main_parent_binding(
                parents, base_sha=job.base_sha, candidate_sha=candidate_sha
            ):
                raise ValueError("anchor fetcher main/tree/parent binding is invalid")
            bundle = Path(raw) / "main.bundle"
            _run_git(
                ["-C", str(stage), "bundle", "create", str(bundle), "refs/heads/main"],
                cwd=Path(raw),
            )
            bundle_raw = bundle.read_bytes()
        machine_policy_app_id = policy.required_check_app_ids.get(
            "TrainCapsule / Machine policy"
        )
        if not isinstance(machine_policy_app_id, int):
            raise ValueError("anchor fetcher Machine-policy App ID is unavailable")
        provisional = ObservedMainReceipt(
            schema_version="3.1",
            observation_id=f"OBS:{job.job_id.replace(':', '_')}",
            repository=job.repository,
            verified_main_sha=main,
            verified_main_tree_sha=tree,
            source_generation_id=job.source_generation_id,
            source_generation_digest=job.source_generation_digest,
            ruleset_observation_digest=model_digest(ruleset),
            required_check_digests=checks,
            github_app_id=machine_policy_app_id,
            observed_at=observed_now,
            expires_at=min(job.expires_at, observed_now + timedelta(minutes=15)),
            issuer_id="ANCHOR:OBSERVER",
            issuer_key_id="KEY:ANCHOR:OBSERVER:ACTIVE",
            signature_algorithm="ed25519",
            signature="A" * 88,
        )
        observed = provisional.model_copy(
            update={"signature": sign_model(provisional, load_private_key(observer_key_raw))}
        )
        request = AnchorUpdateRequest(
            request_id=job.job_id.replace("ANCHORJOB:", "ANCHOR:"),
            repository=job.repository,
            base_sha=job.base_sha,
            merged_main_sha=main,
            merged_main_tree_sha=tree,
            source_generation_id=job.source_generation_id,
            source_generation_digest=job.source_generation_digest,
            observed_main_digest=model_digest(observed),
            ruleset_observation_digest=model_digest(ruleset),
            publication_transaction_digest=sha256_digest(publication_raw),
            bundle_digest=sha256_digest(bundle_raw),
            created_at=observed_now,
            expires_at=min(job.expires_at, observed_now + timedelta(minutes=15)),
        )
        outputs = {
            "observed.json": canonical_json_bytes(observed),
            "ruleset.json": ruleset_raw,
            "publication.json": publication_raw,
            "bundle": bundle_raw,
            "request.json": canonical_json_bytes(request),
        }
        outbox.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(prefix=f".{stem}.", dir=outbox) as raw_stage:
            output_stage = Path(raw_stage)
            for suffix, raw_output in outputs.items():
                _atomic(
                    output_stage / suffix,
                    raw_output,
                    uid=fetcher.pw_uid,
                    gid=fetcher.pw_gid,
                )
            os.replace(output_stage, ready)
            directory = os.open(outbox, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        produced.extend(ready / suffix for suffix in outputs)
    return produced


def promote(
    *,
    outbox: Path = FETCHER_OUTBOX,
    updater_inbox: Path = UPDATER_INBOX,
    observer_public_key_path: Path = CONFIG / "anchor-observer-public-key.pem",
) -> list[Path]:
    """Root-only content-bound promotion; it never signs or authorizes an update."""

    if os.geteuid() != 0:
        raise ValueError("anchor producer promotion requires root")
    fetcher = pwd.getpwnam(FETCHER_USER)
    observer_key = load_public_key(
        _trusted_raw(observer_public_key_path, uid=0, mode=0o444, maximum=16_000)
    )
    promoted: list[Path] = []
    for ready in sorted(outbox.glob("ANCHORJOB_*.ready")):
        if ready.is_symlink() or not ready.is_dir():
            raise ValueError("anchor producer committed output is not a trusted directory")
        with open_trusted_root(ready, expected_uid=fetcher.pw_uid) as frozen:
            raw = {
                suffix: read_bounded_file(
                    frozen,
                    suffix,
                    maximum_bytes=(
                        536_870_912 if suffix == "bundle" else 2_000_000
                    ),
                    required_mode=0o600,
                    expected_file_uid=fetcher.pw_uid,
                )
                for suffix in (
                    "request.json",
                    "observed.json",
                    "ruleset.json",
                    "publication.json",
                    "bundle",
                )
            }
        request = AnchorUpdateRequest.model_validate_json(raw["request.json"], strict=True)
        observed = ObservedMainReceipt.model_validate_json(raw["observed.json"], strict=True)
        verify_model_signature(observed, observer_key)
        if (
            canonical_json_bytes(request) != raw["request.json"]
            or request.observed_main_digest != model_digest(observed)
            or request.bundle_digest != sha256_digest(raw["bundle"])
            or request.publication_transaction_digest != sha256_digest(raw["publication.json"])
        ):
            raise ValueError("anchor producer promotion binding is invalid")
        target_stem = request.request_id.replace(":", "_")
        for source_suffix, target_suffix in (
            ("observed.json", "observed.json"),
            ("ruleset.json", "ruleset.json"),
            ("publication.json", "publication.json"),
            ("bundle", "bundle"),
            ("request.json", "request.json"),
        ):
            target = updater_inbox / f"{target_stem}.{target_suffix}"
            if target.exists():
                if target.read_bytes() != raw[source_suffix]:
                    raise ValueError("anchor producer promotion replay conflicts")
                continue
            _atomic(target, raw[source_suffix], uid=0, gid=0, mode=0o600)
            promoted.append(target)
    return promoted


def askpass() -> int:
    prompt = " ".join(sys.argv[1:]).lower()
    if "username" in prompt:
        print("x-access-token")
    elif "password" in prompt:
        token = os.environ.get("TRAINCAPSULE_GITHUB_PASSWORD")
        if not token or any(character in token for character in "\x00\r\n"):
            return 1
        print(token)
    else:
        return 1
    return 0


def _policy() -> AnchorProducerPolicy:
    raw = _trusted_raw(
        CONFIG / "git-anchor-producer-policy.json", uid=0, mode=0o444, maximum=64_000
    )
    policy = AnchorProducerPolicy.model_validate_json(raw, strict=True)
    if canonical_json_bytes(policy) != raw:
        raise ValueError("anchor producer policy is not canonical")
    return policy


def main() -> int:
    command = sys.argv[1:]
    try:
        if command == ["askpass"]:
            return askpass()
        policy = _policy()
        if command == ["stage-jobs"]:
            stage_jobs(policy)
        elif command == ["produce"]:
            produce(policy)
        elif command == ["promote"]:
            promote()
        else:
            print(
                "usage: traincapsule-verifier-git-anchor-producer "
                "{stage-jobs|produce|promote|askpass}",
                file=sys.stderr,
            )
            return 2
        return 0
    except (KeyError, OSError, ValueError):
        print("Git anchor producer rejected work", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
