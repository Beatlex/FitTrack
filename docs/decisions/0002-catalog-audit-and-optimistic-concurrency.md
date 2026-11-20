# ADR 0002: Catalog audit trail and optimistic concurrency

Status: Accepted for implementation

## Context

Foods and recipes are shared master data. Multiple household members may edit the same record, so last-write-wins updates can silently discard another member's work. Permission changes also need an accountable history. The existing app is deployed locally with SQLite and currently uses additive startup migrations; a later Alembic rollout is planned.

## Decisions

### Audit trail

- Persist catalog and permission events in a dedicated catalog_audit_events table.
- Audit events are append-only at the application layer. A catalog change and its audit event are committed in the same database transaction.
- Record actor ID plus username snapshot, household, entity type/ID/name, action, timestamp, and structured before/after state or permission target.
- Audit shared food/recipe creation, edits, archival/deletion, and actual permission grant/revoke transitions. Idempotent grant requests do not create duplicate events.
- Expose the latest 50 events only to the authenticated household owner. Ordinary members cannot inspect the household-wide audit trail.
- Preserve audit history when an account is deleted, but clear the actor foreign key and replace the username snapshot with Gelöschtes Konto.
- Do not audit personal meal logs, body measurements, goals, or per-user hide/restore actions in this shared catalog log.

### Optimistic concurrency

- Add a monotonically increasing version column to foods and recipes.
- SQLAlchemy mapper versioning adds the current version to ORM UPDATE/DELETE predicates and increments it after a successful write.
- Edit requests carry the version last read by the client. A version mismatch returns HTTP 409 with an instruction to reload; no silent overwrite or automatic merge occurs.
- Recipe metadata and ingredient replacement are one transaction. The version check is flushed before replacing ingredient rows, and any later failure rolls back both the version change and ingredient changes.
- Historical meal nutrient snapshots remain immutable.

### Migration compatibility

- The current startup migration adds the version columns with default 1 and creates the audit table if missing.
- It is additive and idempotent for existing SQLite databases.
- This is a transition migration only; the planned Alembic adoption will take over schema versioning after the database migration/backup design is agreed.

## Consequences

- A stale editor receives a conflict and must reload before applying changes. The application does not attempt an unsafe field-level merge.
- Audit records are transactionally consistent with the changes they describe.
- Audit events are retained after account deletion with the actor anonymized.
- A future audit retention/export policy may be needed as the catalog grows.
