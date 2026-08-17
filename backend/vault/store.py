"""Encrypted document vault — DOC-004.

What this replaces
------------------
v1 wrote generated financial reports to `exports/` on the application's local
disk, unencrypted, named `tax_report_user-123_20260707.pdf`. Forty-one of them
were sitting in the repository when this rebuild started. Anyone with shell
access, a stray backup, or a misconfigured container volume had every user's
income in plain text.

The four properties that matter
--------------------------------
1. **Per-user isolation.** A key is derived from the owner's id and verified on
   every read. Guessing a document id gets you nothing.
2. **Encryption at rest**, delegated to the storage backend (S3 SSE-KMS) rather
   than hand-rolled here. Application-layer crypto written by a tax product is
   a liability, not a feature.
3. **Short-lived signed URLs.** A link that works forever is a credential
   pasted into a support ticket.
4. **Retention.** Documents expire. A tax product accumulating everyone's Form
   16 indefinitely is a DPDP problem waiting to happen (PRD-001).

Design
------
`VaultBackend` is a protocol. `S3Vault` is production; `MemoryVault` exists so
the isolation and expiry properties can be tested without AWS — and those are
exactly the properties worth testing.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Protocol

logger = logging.getLogger(__name__)

DEFAULT_URL_TTL = timedelta(minutes=10)
DEFAULT_RETENTION = timedelta(days=365 * 2)

# Uploads are user-supplied files. Both limits exist so a malformed or hostile
# upload fails at the door rather than inside a parser.
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
ALLOWED_CONTENT_TYPES = frozenset({
    "application/pdf", "text/csv", "application/json",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
})


class DocumentKind(str, Enum):
    FORM_16 = "form_16"
    BROKER_STATEMENT = "broker_statement"
    AIS = "ais"
    EVIDENCE_PACK = "evidence_pack"
    OTHER = "other"


class VaultError(Exception):
    """Storage refused the operation."""


class AccessDenied(VaultError):
    """The caller does not own this document.

    A distinct type so it can never be caught by a broad handler that treats
    every storage failure as "not found" and quietly returns nothing.
    """


@dataclass(frozen=True, slots=True)
class StoredDocument:
    document_id: str
    owner_id: str
    kind: DocumentKind
    filename: str
    content_type: str
    size_bytes: int
    stored_at: datetime
    expires_at: datetime
    content_hash: str

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "kind": self.kind.value,
            "filename": self.filename,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "stored_at": self.stored_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "content_hash": self.content_hash,
            # owner_id is deliberately NOT serialised. It is an access-control
            # input, not something to hand back in a response body.
        }


def object_key(owner_id: str, document_id: str) -> str:
    """Namespace every object under a hash of its owner.

    Hashed rather than raw so the bucket listing does not become a directory of
    user identifiers, and prefixed so an IAM policy can enforce isolation at the
    storage layer as well as here.
    """
    owner_hash = hashlib.sha256(owner_id.encode()).hexdigest()[:32]
    return f"vault/{owner_hash}/{document_id}"


class VaultBackend(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def signed_url(self, key: str, ttl: timedelta) -> str: ...


# ── backends ────────────────────────────────────────────────────────────────

@dataclass(slots=True)
class MemoryVault:
    """In-process backend for tests.

    Not a fallback. `DocumentVault` never selects this on its own — a
    misconfigured production deployment must fail, not quietly start storing
    financial documents in RAM.
    """

    objects: dict[str, bytes] = field(default_factory=dict)
    issued_urls: dict[str, datetime] = field(default_factory=dict)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data

    def get(self, key: str) -> bytes:
        if key not in self.objects:
            raise VaultError(f"no object at {key}")
        return self.objects[key]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def signed_url(self, key: str, ttl: timedelta) -> str:
        token = secrets.token_urlsafe(16)
        self.issued_urls[token] = datetime.now(timezone.utc) + ttl
        return f"memory://{key}?token={token}&expires_in={int(ttl.total_seconds())}"


class S3Vault:
    """Production backend. Server-side encryption is mandatory."""

    def __init__(self, bucket: str, *, kms_key_id: str | None = None,
                 endpoint_url: str | None = None) -> None:
        self.bucket = bucket
        self.kms_key_id = kms_key_id
        self._endpoint_url = endpoint_url
        self._client: Any | None = None

    def _s3(self) -> Any:
        if self._client is None:
            try:
                import boto3
            except ImportError as exc:
                raise VaultError(
                    "boto3 is not installed, so the document vault is "
                    "unavailable. Refusing to fall back to local disk."
                ) from exc
            self._client = boto3.client("s3", endpoint_url=self._endpoint_url)
        return self._client

    def _encryption_args(self) -> dict[str, str]:
        if self.kms_key_id:
            return {"ServerSideEncryption": "aws:kms",
                    "SSEKMSKeyId": self.kms_key_id}
        return {"ServerSideEncryption": "AES256"}

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._s3().put_object(
            Bucket=self.bucket, Key=key, Body=data, ContentType=content_type,
            **self._encryption_args(),
        )

    def get(self, key: str) -> bytes:
        try:
            return self._s3().get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except Exception as exc:
            raise VaultError(f"could not read {key}: {exc}") from exc

    def delete(self, key: str) -> None:
        self._s3().delete_object(Bucket=self.bucket, Key=key)

    def signed_url(self, key: str, ttl: timedelta) -> str:
        return self._s3().generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=int(ttl.total_seconds()),
        )


# ── the vault ───────────────────────────────────────────────────────────────

@dataclass(slots=True)
class DocumentVault:
    """Ownership, validation and retention on top of a storage backend."""

    backend: VaultBackend
    retention: timedelta = DEFAULT_RETENTION
    url_ttl: timedelta = DEFAULT_URL_TTL
    _index: dict[str, StoredDocument] = field(default_factory=dict)

    # ── write ───────────────────────────────────────────────────────────────

    def store(
        self,
        *,
        owner_id: str,
        data: bytes,
        filename: str,
        content_type: str,
        kind: DocumentKind = DocumentKind.OTHER,
        retention: timedelta | None = None,
    ) -> StoredDocument:
        if not owner_id:
            raise VaultError("a document must have an owner")
        if not data:
            raise VaultError("refusing to store an empty document")
        if len(data) > MAX_UPLOAD_BYTES:
            raise VaultError(
                f"document is {len(data):,} bytes, over the "
                f"{MAX_UPLOAD_BYTES:,} byte limit"
            )
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise VaultError(
                f"content type {content_type!r} is not accepted. A tax product "
                f"has no reason to store arbitrary file types."
            )

        document_id = secrets.token_urlsafe(24)
        now = datetime.now(timezone.utc)
        document = StoredDocument(
            document_id=document_id,
            owner_id=owner_id,
            kind=kind,
            filename=filename,
            content_type=content_type,
            size_bytes=len(data),
            stored_at=now,
            expires_at=now + (retention or self.retention),
            content_hash=hashlib.sha256(data).hexdigest(),
        )

        self.backend.put(object_key(owner_id, document_id), data, content_type)
        self._index[document_id] = document
        # Filename and owner are deliberately absent from the log line.
        logger.info("stored document %s (%s, %d bytes)",
                    document_id, kind.value, len(data))
        return document

    # ── read ────────────────────────────────────────────────────────────────

    def _authorised(self, document_id: str, owner_id: str) -> StoredDocument:
        document = self._index.get(document_id)
        if document is None:
            raise VaultError("no such document")
        if document.owner_id != owner_id:
            # Logged as a security event; the caller is told nothing that would
            # confirm the document exists.
            logger.warning(
                "access denied: %s attempted to read document %s",
                owner_id, document_id,
            )
            raise AccessDenied("no such document")
        if document.is_expired:
            raise VaultError(
                f"this document expired on {document.expires_at.date()} under "
                f"the retention policy and is no longer available"
            )
        return document

    def fetch(self, document_id: str, owner_id: str) -> bytes:
        document = self._authorised(document_id, owner_id)
        data = self.backend.get(object_key(owner_id, document_id))

        # Integrity check. Silent corruption in a tax document is worse than a
        # failed read, because the parser downstream would produce figures from
        # it without complaint.
        if hashlib.sha256(data).hexdigest() != document.content_hash:
            raise VaultError(
                f"document {document_id} does not match the hash recorded when "
                f"it was stored. Refusing to return possibly corrupted content."
            )
        return data

    def download_url(self, document_id: str, owner_id: str,
                     ttl: timedelta | None = None) -> str:
        self._authorised(document_id, owner_id)
        return self.backend.signed_url(
            object_key(owner_id, document_id), ttl or self.url_ttl
        )

    def list_for(self, owner_id: str) -> list[StoredDocument]:
        return sorted(
            (d for d in self._index.values()
             if d.owner_id == owner_id and not d.is_expired),
            key=lambda d: d.stored_at,
            reverse=True,
        )

    # ── delete ──────────────────────────────────────────────────────────────

    def delete(self, document_id: str, owner_id: str) -> None:
        self._authorised(document_id, owner_id)
        self.backend.delete(object_key(owner_id, document_id))
        self._index.pop(document_id, None)
        logger.info("deleted document %s", document_id)

    def erase_owner(self, owner_id: str) -> int:
        """Delete everything belonging to one person.

        The DPDP erasure obligation (PRD-001) needs this to be one call that
        provably leaves nothing behind, rather than a loop a caller might get
        wrong.
        """
        ids = [d.document_id for d in self._index.values() if d.owner_id == owner_id]
        for document_id in ids:
            self.backend.delete(object_key(owner_id, document_id))
            self._index.pop(document_id, None)
        logger.info("erased %d document(s) for a data-erasure request", len(ids))
        return len(ids)

    def purge_expired(self) -> int:
        """Retention enforcement, for a scheduled job."""
        expired = [d for d in self._index.values() if d.is_expired]
        for document in expired:
            self.backend.delete(object_key(document.owner_id, document.document_id))
            self._index.pop(document.document_id, None)
        if expired:
            logger.info("purged %d expired document(s)", len(expired))
        return len(expired)


def build_vault(settings: Any = None) -> DocumentVault:
    """Construct the production vault, or fail.

    There is no local-disk fallback and no automatic MemoryVault. A
    misconfigured deployment must refuse to start rather than quietly write
    financial documents somewhere they should not be — which is precisely what
    v1 did with `exports/`.
    """
    if settings is None:
        from backend.config import settings as app_settings

        settings = app_settings

    bucket = getattr(settings.s3, "bucket_name", None)
    if not bucket:
        raise VaultError(
            "no document vault bucket configured. Set AWS_BUCKET_NAME. "
            "There is deliberately no local-disk fallback."
        )
    return DocumentVault(
        backend=S3Vault(
            bucket=bucket,
            kms_key_id=getattr(settings.s3, "kms_key_id", None),
            endpoint_url=getattr(settings.s3, "endpoint_url", None),
        )
    )
