from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend.app.core.config import settings


def _ensure_sqlite_dir(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return
    db_path = Path(database_url.removeprefix("sqlite:///"))
    db_path.parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_dir(settings.database_url)

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


@event.listens_for(Base.metadata, "after_create")
def _create_chunks_fts_table(target, connection, **kwargs) -> None:
    """Runs whenever Base.metadata.create_all() runs (prod startup and every
    test's own engine setup alike), keeping chunks_fts available without
    every caller needing to know about it separately.
    """
    connection.execute(
        text(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                text,
                chunk_id UNINDEXED,
                document_id UNINDEXED,
                chapter_id UNINDEXED,
                material_type UNINDEXED
            )
            """
        )
    )


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
