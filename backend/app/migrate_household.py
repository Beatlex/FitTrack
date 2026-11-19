"""Create household membership and migrate existing shared catalog data.

Run from backend: python -m app.migrate_household
The migration is additive and safe to run more than once.
"""
from sqlalchemy import text

from .database import engine


def upgrade(bind=engine) -> None:
    with bind.begin() as connection:
        connection.execute(text("""CREATE TABLE IF NOT EXISTS households (
            id INTEGER PRIMARY KEY,
            name VARCHAR(80) NOT NULL DEFAULT 'Mein Haushalt',
            owner_id INTEGER NOT NULL REFERENCES users(id),
            created_at DATETIME NOT NULL
        )"""))
        connection.execute(text("""CREATE TABLE IF NOT EXISTS household_members (
            id INTEGER PRIMARY KEY,
            household_id INTEGER NOT NULL REFERENCES households(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role VARCHAR(20) NOT NULL DEFAULT 'member',
            joined_at DATETIME NOT NULL,
            CONSTRAINT uq_household_member UNIQUE(household_id, user_id)
        )"""))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_household_members_household_id ON household_members(household_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_household_members_user_id ON household_members(user_id)"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_household_member_user ON household_members(user_id)"))
        connection.execute(text("""CREATE TABLE IF NOT EXISTS household_invitations (
            id INTEGER PRIMARY KEY,
            household_id INTEGER NOT NULL REFERENCES households(id) ON DELETE CASCADE,
            invited_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            invited_by_user_id INTEGER NOT NULL REFERENCES users(id),
            created_at DATETIME NOT NULL,
            CONSTRAINT uq_household_invitation_target UNIQUE(household_id, invited_user_id)
        )"""))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_household_invitations_household_id ON household_invitations(household_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_household_invitations_invited_user_id ON household_invitations(invited_user_id)"))

        food_columns = {row[1] for row in connection.execute(text("PRAGMA table_info(foods)"))}
        if "household_id" not in food_columns:
            connection.execute(text("ALTER TABLE foods ADD COLUMN household_id INTEGER REFERENCES households(id)"))
        recipe_columns = {row[1] for row in connection.execute(text("PRAGMA table_info(meal_templates)"))}
        if "household_id" not in recipe_columns:
            connection.execute(text("ALTER TABLE meal_templates ADD COLUMN household_id INTEGER REFERENCES households(id)"))

        # Do not create a household implicitly. Accounts remain independent until
        # a user explicitly creates a household or accepts an invitation.
        # If an older migration already created a legacy household, preserve its
        # existing membership and shared catalogue assignments.
        household_id = connection.execute(
            text("SELECT id FROM households ORDER BY id LIMIT 1")
        ).scalar()
        if household_id is not None:
            connection.execute(
                text("UPDATE foods SET household_id = :household WHERE household_id IS NULL AND is_shared = 1"),
                {"household": household_id},
            )
            connection.execute(
                text("UPDATE meal_templates SET household_id = :household WHERE household_id IS NULL AND is_shared = 1"),
                {"household": household_id},
            )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_foods_household_id ON foods(household_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_meal_templates_household_id ON meal_templates(household_id)"))


if __name__ == "__main__":
    upgrade()
    print("Household schema is up to date.")
