from collections.abc import Iterator
from time import perf_counter

from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.observability import database_stats


def create_database_engine(settings: Settings) -> Engine:
    engine = create_engine(
        URL.create("sqlite", database=str(settings.database_path)),
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute(f"PRAGMA busy_timeout={settings.sqlite_busy_timeout_ms}")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    @event.listens_for(engine, "before_cursor_execute")
    def before_query(_conn, _cursor, _statement, _parameters, context, _many):
        context._dbo_started = perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def after_query(_conn, _cursor, _statement, _parameters, context, _many):
        stats = database_stats.get()
        if stats is not None:
            stats["count"] += 1
            stats["ms"] += (perf_counter() - context._dbo_started) * 1000

    return engine


def get_session(request: Request) -> Iterator[Session]:
    # Callers explicitly commit short write transactions; closing rolls back unfinished work.
    factory: sessionmaker[Session] = request.app.state.sessions
    with factory() as session:
        yield session
