from pathlib import Path
import re
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker, Session
from backend.app.core.config import settings
from backend.app.models.base import Base


def build_engine(url, source=False):
    parsed = make_url(url)
    sqlite = parsed.get_backend_name() == 'sqlite'
    kwargs = {'pool_pre_ping': True}
    if sqlite:
        from sqlalchemy.pool import StaticPool
        kwargs.update(connect_args={'check_same_thread': False})
        if parsed.database in (None, '', ':memory:'):
            kwargs['poolclass'] = StaticPool
    else:
        kwargs.update(pool_size=2 if source else settings.DB_POOL_SIZE,
                      max_overflow=0 if source else settings.DB_MAX_OVERFLOW,
                      pool_timeout=settings.DB_POOL_TIMEOUT_SECONDS,
                      pool_recycle=1800, connect_args={'timeout': 10})
        if source:
            kwargs['isolation_level'] = 'AUTOCOMMIT'
    engine = create_engine(url, **kwargs)
    if not sqlite:
        @event.listens_for(engine, 'connect')
        def query_timeout(connection, record):
            connection.timeout = settings.DB_QUERY_TIMEOUT_SECONDS
    if sqlite and not source:
        @event.listens_for(engine, 'connect')
        def attach_schemas(connection, record):
            # Explicit BEGIN avoids sqlite legacy SAVEPOINT commits outside a
            # transaction, keeping batch rollback equivalent to SQL Server.
            connection.isolation_level = None
            cursor = connection.cursor()
            cursor.execute('PRAGMA foreign_keys=ON')
            for schema in ['master', 'integration', 'attendance', 'security', 'system']:
                if settings.APP_ENV == 'test':
                    filename = ':memory:'
                else:
                    root = Path(parsed.database).resolve().parent
                    filename = str(root / (schema + '.db'))
                cursor.execute(f'ATTACH DATABASE ? AS {schema}', (filename,))
            cursor.close()
        @event.listens_for(engine, 'begin')
        def begin_sqlite(connection):
            connection.exec_driver_sql('BEGIN')
    if source and not (sqlite and settings.APP_ENV == 'test'):
        @event.listens_for(engine, 'before_cursor_execute')
        def source_read_only(connection, cursor, statement, parameters, context, executemany):
            # The production source is SELECT-only, including setup/maintenance code.
            if not statement.lstrip().upper().startswith('SELECT') or ';' in statement.rstrip().rstrip(';') or re.search(r'\bINTO\b|\bEXEC(?:UTE)?\b|OPENROWSET|OPENDATASOURCE', statement, re.I):
                raise PermissionError('Production source database is read-only; only SELECT is permitted')
    return engine


target_engine = build_engine(settings.get_target_db_url())
source_engine = build_engine(settings.get_source_db_url(), source=True)
TargetSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=target_engine)
SourceSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=source_engine)

# Register transactional change capture for both API and worker sessions.
from backend.app.services import change_events  # noqa: E402,F401


def get_db() -> Generator[Session, None, None]:
    with TargetSessionLocal() as db:
        yield db


def get_source_db() -> Generator[Session, None, None]:
    with SourceSessionLocal() as db:
        yield db
