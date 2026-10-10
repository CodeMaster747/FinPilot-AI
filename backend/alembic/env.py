"""Alembic environment. Uses the app's own engine so paths with spaces etc. need no URL escaping."""

from alembic import context

import app.models  # noqa: F401  (register all tables)
from app.db.base import Base
from app.db.session import get_engine

target_metadata = Base.metadata


def _run(connection) -> None:  # noqa: ANN001
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # SQLite needs batch mode for ALTER TABLE
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = context.config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    with get_engine().connect() as conn:
        _run(conn)
        conn.commit()


run_migrations_online()
