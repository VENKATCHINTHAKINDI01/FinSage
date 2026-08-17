"""Encrypted document vault — DOC-004.

The acceptance criteria are security properties, and every one of them is
testable without AWS. That is why `MemoryVault` exists.

The tests that matter: cross-user access is denied, URLs expire, expired
documents are gone, and there is no path that writes a user's financial
document to local disk.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from backend.vault.store import (
    MAX_UPLOAD_BYTES,
    AccessDenied,
    DocumentKind,
    DocumentVault,
    MemoryVault,
    S3Vault,
    VaultError,
    build_vault,
    object_key,
)

PDF = "application/pdf"


@pytest.fixture
def vault() -> DocumentVault:
    return DocumentVault(backend=MemoryVault())


def _store(v: DocumentVault, owner: str = "alice", **kw):
    return v.store(
        owner_id=owner,
        data=kw.pop("data", b"%PDF-1.4 form 16 contents"),
        filename=kw.pop("filename", "form16.pdf"),
        content_type=kw.pop("content_type", PDF),
        kind=kw.pop("kind", DocumentKind.FORM_16),
        **kw,
    )


# ══ per-user isolation — the property that matters most ═════════════════════

class TestIsolation:
    def test_another_user_cannot_fetch_your_document(self, vault) -> None:
        doc = _store(vault, "alice")
        with pytest.raises(AccessDenied):
            vault.fetch(doc.document_id, "mallory")

    def test_another_user_cannot_get_a_download_url(self, vault) -> None:
        doc = _store(vault, "alice")
        with pytest.raises(AccessDenied):
            vault.download_url(doc.document_id, "mallory")

    def test_another_user_cannot_delete_your_document(self, vault) -> None:
        doc = _store(vault, "alice")
        with pytest.raises(AccessDenied):
            vault.delete(doc.document_id, "mallory")
        assert vault.fetch(doc.document_id, "alice")

    def test_denial_does_not_confirm_the_document_exists(self, vault) -> None:
        """An attacker probing ids must not be able to tell 'yours, denied'
        from 'no such thing'."""
        doc = _store(vault, "alice")
        with pytest.raises(AccessDenied) as denied:
            vault.fetch(doc.document_id, "mallory")
        with pytest.raises(VaultError) as missing:
            vault.fetch("does-not-exist", "mallory")
        assert str(denied.value) == str(missing.value) == "no such document"

    def test_listing_shows_only_your_own(self, vault) -> None:
        _store(vault, "alice")
        _store(vault, "alice")
        _store(vault, "bob")
        assert len(vault.list_for("alice")) == 2
        assert len(vault.list_for("bob")) == 1
        assert vault.list_for("carol") == []

    def test_object_keys_are_namespaced_and_do_not_leak_the_user_id(self) -> None:
        """So a bucket listing is not a directory of user identifiers, and an
        IAM prefix policy can enforce isolation at the storage layer too."""
        key = object_key("alice@example.com", "doc123")
        assert key.startswith("vault/")
        assert "alice" not in key
        assert key.endswith("doc123")

    def test_two_users_never_collide(self) -> None:
        assert object_key("alice", "d1") != object_key("bob", "d1")

    def test_owner_id_is_not_serialised(self, vault) -> None:
        """It is an access-control input, not something to hand back."""
        assert "owner_id" not in _store(vault, "alice").to_dict()


# ══ signed URLs expire ══════════════════════════════════════════════════════

class TestSignedUrls:
    def test_a_url_carries_an_expiry(self, vault) -> None:
        doc = _store(vault, "alice")
        url = vault.download_url(doc.document_id, "alice", ttl=timedelta(minutes=5))
        assert "expires_in=300" in url

    def test_the_default_ttl_is_short(self, vault) -> None:
        """A link that works forever is a credential pasted into a support
        ticket."""
        assert vault.url_ttl <= timedelta(minutes=15)


# ══ retention ═══════════════════════════════════════════════════════════════

class TestRetention:
    def test_an_expired_document_cannot_be_fetched(self, vault) -> None:
        doc = _store(vault, "alice", retention=timedelta(seconds=-1))
        assert doc.is_expired
        with pytest.raises(VaultError, match="retention policy"):
            vault.fetch(doc.document_id, "alice")

    def test_expired_documents_do_not_appear_in_listings(self, vault) -> None:
        _store(vault, "alice", retention=timedelta(seconds=-1))
        _store(vault, "alice")
        assert len(vault.list_for("alice")) == 1

    def test_purge_removes_them_from_storage(self, vault) -> None:
        _store(vault, "alice", retention=timedelta(seconds=-1))
        _store(vault, "alice")
        assert vault.purge_expired() == 1
        assert len(vault.backend.objects) == 1


# ══ DPDP erasure ════════════════════════════════════════════════════════════

def test_erasing_a_user_leaves_nothing_behind(vault) -> None:
    """One call, provably complete. The erasure obligation is not something to
    implement as a loop each caller might get wrong."""
    _store(vault, "alice")
    _store(vault, "alice")
    _store(vault, "bob")

    assert vault.erase_owner("alice") == 2
    assert vault.list_for("alice") == []
    assert len(vault.backend.objects) == 1, "bob's document must survive"
    assert len(vault.list_for("bob")) == 1


# ══ input validation ════════════════════════════════════════════════════════

class TestValidation:
    def test_an_empty_document_is_refused(self, vault) -> None:
        with pytest.raises(VaultError, match="empty"):
            _store(vault, data=b"")

    def test_an_oversized_upload_is_refused(self, vault) -> None:
        with pytest.raises(VaultError, match="over the"):
            _store(vault, data=b"x" * (MAX_UPLOAD_BYTES + 1))

    @pytest.mark.parametrize(
        "content_type",
        ["application/x-msdownload", "text/html", "image/svg+xml",
         "application/octet-stream"],
    )
    def test_unexpected_content_types_are_refused(self, vault, content_type) -> None:
        """A tax product has no reason to store arbitrary file types, and every
        one it accepts is another parser to harden."""
        with pytest.raises(VaultError, match="not accepted"):
            _store(vault, content_type=content_type)

    @pytest.mark.parametrize("content_type", ["application/pdf", "text/csv",
                                              "application/json"])
    def test_expected_types_are_accepted(self, vault, content_type) -> None:
        assert _store(vault, content_type=content_type).content_type == content_type

    def test_a_document_needs_an_owner(self, vault) -> None:
        with pytest.raises(VaultError, match="must have an owner"):
            _store(vault, owner="")


# ══ integrity ═══════════════════════════════════════════════════════════════

def test_corrupted_content_is_refused_not_returned(vault) -> None:
    """Silent corruption in a tax document is worse than a failed read: the
    parser downstream would produce figures from it without complaint."""
    doc = _store(vault, "alice")
    vault.backend.objects[object_key("alice", doc.document_id)] = b"tampered"

    with pytest.raises(VaultError, match="does not match the hash"):
        vault.fetch(doc.document_id, "alice")


def test_a_round_trip_returns_exactly_what_was_stored(vault) -> None:
    payload = b"%PDF-1.4 the actual bytes"
    doc = _store(vault, "alice", data=payload)
    assert vault.fetch(doc.document_id, "alice") == payload


# ══ no local disk, no silent fallback ═══════════════════════════════════════

class TestNoLocalDiskFallback:
    def test_an_unconfigured_vault_refuses_to_build(self) -> None:
        """v1 wrote 41 unencrypted financial PDFs to `exports/`. A
        misconfigured deployment must fail, not find somewhere to write."""
        class NoBucket:
            class s3:
                bucket_name = ""

        with pytest.raises(VaultError, match="no local-disk fallback"):
            build_vault(NoBucket())

    def test_build_vault_never_selects_the_memory_backend(self) -> None:
        class Configured:
            class s3:
                bucket_name = "finsage-documents"
                kms_key_id = None
                endpoint_url = None

        assert isinstance(build_vault(Configured()).backend, S3Vault)

    def test_the_s3_backend_always_requests_encryption(self) -> None:
        assert S3Vault("b")._encryption_args()["ServerSideEncryption"] == "AES256"

    def test_a_kms_key_is_used_when_configured(self) -> None:
        args = S3Vault("b", kms_key_id="arn:aws:kms:key/abc")._encryption_args()
        assert args["ServerSideEncryption"] == "aws:kms"
        assert args["SSEKMSKeyId"] == "arn:aws:kms:key/abc"

    def test_a_missing_boto3_fails_rather_than_degrading(self, monkeypatch) -> None:
        import builtins

        real_import = builtins.__import__

        def no_boto3(name, *args, **kwargs):
            if name == "boto3":
                raise ImportError("no boto3")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_boto3)
        with pytest.raises(VaultError, match="Refusing to fall back to local disk"):
            S3Vault("bucket")._s3()


# ══ metadata ════════════════════════════════════════════════════════════════

def test_stored_metadata(vault) -> None:
    doc = _store(vault, "alice", filename="form16_2027.pdf",
                 kind=DocumentKind.FORM_16)
    d = doc.to_dict()
    assert d["kind"] == "form_16"
    assert d["filename"] == "form16_2027.pdf"
    assert d["size_bytes"] > 0
    assert len(d["content_hash"]) == 64


def test_document_ids_are_unguessable(vault) -> None:
    ids = {_store(vault, "alice").document_id for _ in range(20)}
    assert len(ids) == 20
    assert all(len(i) >= 24 for i in ids)


# ══ the regression guard ════════════════════════════════════════════════════

def test_no_module_writes_a_user_document_to_local_disk() -> None:
    """The hole DOC-004 closes, kept closed.

    `report_generator.py` contained:

        file_path = f"/Users/<a developer>/…/exports/{user_id}/{file_name}"
        with open(filepath, 'wb') as f:
            f.write(pdf_content)

    — a hardcoded absolute path from one machine, receiving unencrypted PDFs
    of named users' income. Three separate call sites did it.

    Any reintroduction fails here rather than in production.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3] / "backend"
    offenders: list[str] = []

    for module in root.rglob("*.py"):
        if "tests" in module.parts or "vault" in module.parts:
            continue
        source = module.read_text(encoding="utf-8")
        rel = module.relative_to(root.parent)

        # A binary write in a module that also handles report or document
        # content is the shape of the bug.
        if "'wb'" in source or '"wb"' in source:
            offenders.append(f"{rel}: binary file write")
        if "/Users/" in source or "/home/" in source:
            offenders.append(f"{rel}: hardcoded absolute home path")
        if "exports/" in source and "open(" in source:
            offenders.append(f"{rel}: writes into exports/")

    assert not offenders, (
        "user documents must go to the vault, not the filesystem:\n  "
        + "\n  ".join(offenders)
    )
