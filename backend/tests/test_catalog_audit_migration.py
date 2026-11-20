from sqlalchemy import Column, DateTime, Integer, MetaData, Table, create_engine, inspect, text

from app.migrate_catalog_audit import upgrade


def test_catalog_audit_migration_adds_versions_and_is_idempotent() -> None:
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Table("households", metadata, Column("id", Integer, primary_key=True))
    foods = Table("foods", metadata, Column("id", Integer, primary_key=True), Column("created_at", DateTime))
    recipes = Table("meal_templates", metadata, Column("id", Integer, primary_key=True), Column("created_at", DateTime))
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(foods.insert().values(id=1))
        connection.execute(recipes.insert().values(id=1))

    upgrade(engine)
    upgrade(engine)

    inspector = inspect(engine)
    assert {"version", "updated_at"} <= {column["name"] for column in inspector.get_columns("foods")}
    assert {"version", "updated_at"} <= {column["name"] for column in inspector.get_columns("meal_templates")}
    assert "catalog_audit_events" in inspector.get_table_names()

    with engine.connect() as connection:
        assert connection.execute(text("SELECT version FROM foods")).scalar_one() == 1
        assert connection.execute(text("SELECT version FROM meal_templates")).scalar_one() == 1
        assert connection.execute(text("SELECT updated_at FROM foods")).scalar_one() is not None
        assert connection.execute(text("SELECT updated_at FROM meal_templates")).scalar_one() is not None

    engine.dispose()
