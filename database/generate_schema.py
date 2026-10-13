"""Render metadata DDL to disk without opening any database connection."""
from pathlib import Path
from sqlalchemy.dialects import mssql
from sqlalchemy.schema import CreateTable, CreateIndex
from backend.app.models import Base


def generate():
    dialect = mssql.dialect()
    statements = ["-- Empty database setup only. Existing production upgrades use database.migrate_production."]
    for schema in sorted({table.schema for table in Base.metadata.tables.values()}):
        statements.append(f"IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = '{schema}') EXEC('CREATE SCHEMA [{schema}]');")
    for table in Base.metadata.sorted_tables:
        statements.append(str(CreateTable(table).compile(dialect=dialect)))
        statements.extend(str(CreateIndex(index).compile(dialect=dialect)) for index in sorted(table.indexes, key=lambda item: item.name))
    Path('database/schema.sql').write_text('\nGO\n'.join(statements) + '\nGO\n', encoding='utf-8')


if __name__ == '__main__':
    generate()
