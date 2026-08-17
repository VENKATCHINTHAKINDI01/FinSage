# DPDP Act 2023 — obligations mapped to implemented controls

Last reviewed 2026-08-16.

This table exists because v1's README claimed compliance with nothing behind
it. A claim of compliance is a representation to users about how their data is
handled, and an unbacked one is worse than saying nothing.

**Read the status column literally.** `implemented` means there is code and a
test. `partial` means some of the obligation is met and the rest is named.
`not started` means exactly that. Nothing here is marked done because it is
planned.

| Obligation | Section | Control | Status |
|---|---|---|---|
| Itemised notice, plain language, versioned | s.5 | `Notice` carries per-purpose text and a version; a purpose the notice does not describe cannot be consented to | implemented |
| Consent free, specific, informed, per purpose | s.6(1) | `Purpose` is a closed enum; `ConsentRecord` is per principal per purpose, persisted in Postgres (`consent_records`, PRD-001) | implemented |
| Consent tied to the notice the person actually read | s.6(1) | Consent records the notice version; a reworded purpose invalidates it and forces re-consent | implemented |
| Withdrawal as easy as granting | s.6(6) | `POST /api/v1/consent/withdraw` takes the same body shape as `POST /api/v1/consent/grant`; the underlying `withdraw()`/`grant()` signature symmetry is asserted by a test | implemented |
| Processing ceases on withdrawal | s.6(6) | `require_consent` raises; withdrawn data becomes due for erasure immediately | implemented |
| Data minimisation / purpose limitation | s.6(1) | `require_consent_dep()` (`backend/api/consent.py`) is a ready-to-use FastAPI dependency; applied to the consent/access routes themselves | partial — the check exists and is callable; not yet applied to document upload, chat, procurement or reports, each of which needs its own purpose |
| Erasure when purpose is served | s.8(7) | `due_for_erasure` returns exactly what a scheduled job must delete today | implemented |
| Retention periods stated and enforced | s.8(7) | `RETENTION_DAYS` per purpose; tax records held longer for the ITR-U window; full inventory in `docs/dpdp_register.md` | implemented |
| Erasure across every store, verified | s.8(7) | `erase()` returns a receipt per store; an unconfirmable delete is a failure. Postgres stores have an obvious deleter/confirmer pair; the document vault and vector store do not have one wired yet (`docs/dpdp_register.md`, gap 1) | partial |
| Accuracy and completeness | s.8(3) | `POST /api/v1/profile` already edits the account's financial-profile fields; no separate correction endpoint exists because a second path editing the same rows would drift from the first | implemented |
| Security safeguards | s.8(5) | Encrypted document vault (DOC-004); secret audit at startup (PRD-005); refresh rotation with reuse detection (PRD-002); per-user/IP rate limiting and magic-byte upload validation (PRD-003) | partial |
| No PII in logs | s.8(5) | `RedactingFormatter` applied at the formatter, redacting PAN, GSTIN, Aadhaar (Verhoeff-checked), email, phone | implemented |
| Breach notification to the Board and to affected principals | s.8(6) | Procedure in `docs/runbook.md` § Breach notification: containment, scoping, Board and principal notification steps | implemented as a written, unrehearsed procedure — see status note there |
| Grievance redressal | s.8(9), s.13 | `Notice` carries the officer and contact (`GET /api/v1/consent/notice`); no intake/ticketing endpoint yet, contact is an email address | partial |
| Right to access information about processing | s.11 | `GET /api/v1/me/data` returns account, financial-profile and consent-ledger data | partial — covers Postgres-resident structured data; documents in the vault and vector-store content are not yet included (`docs/dpdp_register.md`, gap 1) |
| Right to correction and erasure | s.12 | Correction via `POST /api/v1/profile`; erasure logic (`erase()`) implemented but not exposed as a self-serve endpoint — currently a manual process using the pure function | partial |
| Right to nominate | s.14 | — | not started |
| Children's data — verifiable parental consent | s.9 | — | not started; the product does not knowingly serve under-18s and has no age gate, which is itself a gap |
| Data-processing register | s.8(1) | `docs/dpdp_register.md` — every store, what it holds, why, and for how long, plus the processors data is shared with | implemented — maintained by hand, no CI check for staleness yet |

## What is deliberately not claimed

There is no Data Protection Impact Assessment, no independent audit and no
Data Protection Officer appointment. Those attach to a **Significant** Data
Fiduciary under s.10, and that designation is made by the Central Government —
it is not self-assessed. If this product is notified as one, s.10 obligations
apply and none of them are met today.

## The next three things

1. Call `require_consent_dep()` from document upload, chat, procurement and
   reports — the dependency is written and used by the consent routes
   themselves; the remaining wiring is what makes purpose limitation real
   product-wide rather than only where this pass touched.
2. Wire the document vault and vector store into `erase()`'s
   deleter/confirmer protocol so `docs/dpdp_register.md` gap 1 closes and a
   self-serve erasure endpoint becomes safe to expose.
3. Rehearse the breach-notification procedure once, the same way the restore
   drill in `docs/runbook.md` is scheduled — a written procedure nobody has
   run is a plan, not a capability.
