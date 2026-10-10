from alembic import context

from app.config import Settings
from app.database import create_database_engine
from app.models import Base

settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
engine = create_database_engine(settings)
try:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
finally:
    engine.dispose()
