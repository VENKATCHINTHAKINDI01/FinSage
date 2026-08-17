"""Encrypted document vault.

Per-user isolation, encryption at rest, short-lived signed URLs, retention.

There is deliberately no local-disk backend. v1 wrote 41 unencrypted financial
PDFs to `exports/`; a misconfigured deployment must now refuse to start rather
than find somewhere to write.
"""

from backend.vault.store import (
    AccessDenied,
    DocumentKind,
    DocumentVault,
    MemoryVault,
    S3Vault,
    StoredDocument,
    VaultError,
    build_vault,
)

__all__ = [
    "AccessDenied",
    "DocumentKind",
    "DocumentVault",
    "MemoryVault",
    "S3Vault",
    "StoredDocument",
    "VaultError",
    "build_vault",
]
