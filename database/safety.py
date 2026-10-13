"""Prevent development utilities from seeding or clearing production data."""
import sys
from sqlalchemy.engine import make_url
from backend.app.core.config import settings


def require_development_data_operation(sql_server_utility=False):
    if sql_server_utility:
        raise RuntimeError("Legacy SQL Server data utilities are disabled; use schema-only migrations")
    if '--allow-development-data' not in sys.argv or settings.APP_ENV not in ('development', 'test'):
        raise RuntimeError('Data-changing setup/reset utilities are disabled; use target-only schema migrations')
    source = make_url(settings.get_source_db_url())
    target = make_url(settings.get_target_db_url())
    if source.get_backend_name() != 'sqlite' or target.get_backend_name() != 'sqlite':
        raise RuntimeError('Development data utilities may operate only on isolated SQLite databases')
