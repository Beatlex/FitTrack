# ADR 0001: Catalog access, ownership, and account deletion

Status: Accepted for implementation

## Context

The current catalog uses `household_id` as the visibility boundary. This is sufficient for household-wide sharing but cannot represent per-member grants or per-member hiding. Recipe deletion is currently physical while food deletion is an archive, which is inconsistent for shared records. Account deletion is not yet implemented and must not cascade-delete catalog entries still used by other household members.

## Decision

### Ownership and access are separate

- Foods and recipes retain a nullable `owner_id` identifying the creator while that account exists.
- Access is represented by normalized relational grant rows, not serialized ID arrays.
- A grant is explicit per user. Household-wide sharing is implemented by granting access to current members; accepting an invitation grants access to eligible household-shared entries.
- A per-user hidden/withdrawn state is separate from access. Hiding an item never deletes it for another user.
- Recipe ingredient resolution is a contextual grant scoped to a recipe, food, and user. It does not make the food visible in the general food picker.
- The API derives the acting user from the authenticated session and checks access on every read and mutation. Client-supplied user IDs are never authorization inputs.

### Delete semantics

- “Remove from my catalog” withdraws or hides the current user's access. It does not physically delete a shared item.
- Physical deletion is allowed only when no other user has access and no retained records depend on the item. Otherwise the item is archived or retained.
- Editing shared food and recipe data remains available to household members. Nutrient snapshots in already logged meals remain immutable.
- Account deletion is a separate, explicit operation. It removes credentials and personal data (measurements, goals, personal meal logs and favorites), revokes pending invitations and memberships, and removes the deleted user's grants.
- Catalog records still granted to other users are retained. Their owner reference becomes null and audit/display metadata uses a neutral deleted-account label. Private records with no remaining grants are deleted when safe; referenced foods are retained as archived records until dependencies are removed.
- If the deleted account owns a household, deletion must not silently remove other members. Ownership is transferred to an eligible remaining member through an explicit transaction; otherwise household dissolution follows a documented last-member path.

### Migration and compatibility

- Existing household catalog visibility must be migrated into per-user grants for every current household member.
- Existing private catalog records receive a grant for their owner.
- Migration must be additive, idempotent, transactional, and preserve IDs and historical nutrient snapshots.
- The legacy `household_id` field is retained during rollout as provenance/compatibility metadata. It is not the long-term authorization source once grant-based checks are enabled.

## Implementation status

1. **Complete:** Grant/hidden tables, contextual recipe-ingredient grants, constraints, indexes, and idempotent migration/backfill.
2. **Complete:** Catalog reads, writes, recipe ingredient resolution, meal logging, and household lifecycle now use the grant model.
3. **Complete:** Personal hide/restore endpoints and safe removal behavior for shared records.
4. **Complete:** Password- and username-confirmed account deletion with household-owner transfer, shared recipe ownership transfer, personal-data cleanup, and dependency retention.
5. **Complete:** Frontend controls for personal food/recipe hide and restore.
6. **Complete:** Household-admin permission matrix for granting/revoking individual food and recipe access. Recipe grants include only contextual ingredient-resolution grants; they do not expose ingredients in the general food picker.
7. **Complete:** Frontend account-deletion flow with current-password verification, exact username confirmation, and a final irreversible-action confirmation.
8. **Complete:** Append-only audit events for catalog creation, edits, archival/deletion, and actual per-member permission transitions. Household audit history is admin-only; deleted actors are anonymized.
9. **Complete:** Optimistic version checks for concurrent food/recipe edits. Stale writes return HTTP 409 and cannot overwrite a newer version.
10. **Follow-up:** Timezone standardization and the Alembic/database backup operations plan.

## Security and integrity requirements

- Unique constraints prevent duplicate grants and hidden markers.
- Contextual ingredient grants never imply general catalog visibility.
- Grant management is restricted to the authenticated household owner; target users and catalog records must belong to that same household.
- The household owner and the creator of a catalog record cannot have their access revoked through member-level controls.
- Recipe grant/revoke operations create or remove only the corresponding recipe-scoped ingredient grants.
- No polymorphic foreign key or JSON/array of user IDs is used.
- Database foreign keys and transaction boundaries protect recipe-to-food dependencies.
- Tests cover cross-user IDOR attempts, revoked access, member departure, account deletion, and retained shared dependencies.
