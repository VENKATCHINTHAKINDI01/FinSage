# Incident runbook — PRD-006

## Status: written, not drilled

The restore procedure below has **never been executed**. PRD-006 is
`implemented`, not `verified`, and the acceptance criterion "restore drill
executed successfully from backup" is unmet. A backup nobody has restored from
is a backup nobody knows they have.

## Top five failure modes

### 1. The app will not start
Almost always PRD-005: `enforce()` refuses on a placeholder or missing
`AUTH__SECRET_KEY`. The message names the variable. This is working as
intended — an app that boots on a published secret authenticates nobody.

### 2. Every request 401s after a deploy
Check whether `AUTH__SECRET_KEY` changed. Every existing token was signed with
the old one and is now invalid. This is a forced logout, not a bug; it is the
cost of rotation and the rotation procedure should have said so.

### 3. LLM outage
Deterministic answers continue — the purity contract means `backend.core`
cannot reach an LLM, so every figure is computed without one. Explanations
stop. Confirm the degradation notice is visible rather than a silent partial.

### 4. Runaway LLM spend
Per-user daily caps (PRD-003) reserve before the call. If spend still runs
away, the reservation is being skipped or the estimate is far below actual —
check the reconcile deltas before raising the cap.

### 5. Source gatherer failing
Nothing breaks: cached facts serve with a staleness badge and ungathered ones
become named gaps. The real risk is silence — nobody sees a rate change until
the canary is fixed, so treat a failing canary as urgent even though nothing
is down.

## Restore drill — the procedure to run, not a record of having run it

1. Provision an empty database.
2. Restore the most recent nightly dump.
3. Assert row counts against the source for `users`, `sessions`,
   `tax_calculations`.
4. Run the golden corpus against the restored data — the numbers must match,
   not merely compute.
5. Record the wall-clock time. That number is the recovery time objective, and
   until the drill runs there is no RTO, only a hope.

## Zero-downtime migrations

Expand, migrate, contract. Add the column nullable, backfill, start writing to
it, then stop reading the old one, then drop it — four deploys, not one.

PRD-002's `jti`/`family`/`state`/`replaced_by` fields landed as a **new**
`refresh_sessions` table (the `prd_002_refresh_sessions` migration) rather
than as columns bolted onto the existing `sessions` table — a new
table with no readers yet needs no expand/contract dance, and keeping it
separate means `sessions` (an access-token audit trail nothing reads back)
and `refresh_sessions` (read and written on every refresh) do not have to
share one migration history. The pattern above still applies to the next
change that alters a column something is already reading.

## Breach notification — s.8(6)

**Status: procedure written, never exercised. No breach has occurred; this is
preparation, not a record.**

DPDP s.8(6) requires the Data Fiduciary to notify the Data Protection Board
and each affected Data Principal of a personal data breach, "in such form and
manner as may be prescribed" — the Rules had not prescribed a form or a
deadline as of this writing, so the procedure below over-delivers on speed and
content rather than wait for the specifics.

### What counts as a breach

Any of: unauthorised access to `users`, `financial_profiles`, `consent_records`
or `refresh_sessions`; a leaked `AUTH__SECRET_KEY` (every session forgeable);
an exposed S3/MinIO document-vault credential; a database backup or dump
reachable outside its intended access; a third-party processor (LLM provider,
email/SMS gateway) disclosing an incident that involved this product's data.

**A revoked session family from PRD-002's reuse detection is not, by itself, a
breach.** It is the control working — evidence of an attempted token theft
that was contained, not confirmation that data left the system. Treat repeated
reuse-detection events from the same account as a signal worth investigating,
not an automatic trigger for this procedure.

### Immediate response (target: within 1 hour of confirmation)

1. **Contain.** Rotate `AUTH__SECRET_KEY` if credentials are implicated (this
   invalidates every session — see failure mode 2 above, and warn users it is
   coming). Revoke the specific IAM/DB credentials if a store was the vector.
   Take the affected route or store offline if containment requires it.
2. **Preserve.** Snapshot logs and DB state *before* remediating — the
   `RedactingFormatter` (PRD-004) means logs should not themselves contain PAN,
   Aadhaar or tokens, but preserve them anyway for the "what was accessed"
   question the Board and affected users will both ask.
3. **Scope.** Which table(s), which principal ids, which fields, what time
   window. `consent_records` and `refresh_sessions` both carry `principal_id`
   and timestamps, so a scoped query answers "who" and "when" directly.

### Notification (target: within 72 hours, ahead of any prescribed deadline)

4. **To the Data Protection Board:** what happened, what data, how many
   principals, containment steps taken, remediation in progress. Use the
   Board's prescribed form once one exists; until then, the four items above
   in writing, dated, from the grievance officer of record
   (`CURRENT_NOTICE.grievance_officer` in `backend/api/consent.py`).
5. **To affected principals:** plain language, what data of theirs was
   involved, what they should do (e.g. re-authenticate, watch for phishing
   referencing real account details), and the grievance contact. Sent to every
   principal in the scoped set from step 3 — not a blog post, a direct
   notification, because s.8(6) names the principal as the recipient.
6. **Internal:** a dated incident record — start time, confirmation time,
   containment time, notification time, root cause, and the fix that prevents
   recurrence. This is also the record a regulator asks for after the fact.

### What is missing

No dedicated incident-management tooling, no on-call rotation, no rehearsed
drill of this procedure (unlike the restore drill above, which is at least
scheduled as future work — this has not been either). The Board's prescribed
form and deadline, once published under the Rules, should replace the
"72 hours" placeholder above rather than layer on top of it.
