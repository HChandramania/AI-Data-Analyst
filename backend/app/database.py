from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings


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

    return engine


def get_session(request: Request) -> Iterator[Session]:
    # Callers explicitly commit short write transactions; closing rolls back unfinished work.
    factory: sessionmaker[Session] = request.app.state.sessions
    with factory() as session:
        yield session
