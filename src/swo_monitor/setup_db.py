"""Create the database and its tables. Safe to run more than once.

Run it with:  uv run swo-setup-db
"""

import re

from swo_monitor.config import DB_NAME, SCHEMA_FILE
from swo_monitor.db import get_connection


def create_database() -> None:
    """Create the database if it does not exist yet."""
    # A database name cannot be passed as a query parameter, so it is placed in the
    # SQL text directly. Checking it first means a strange value in .env cannot
    # change what the statement does.
    if not re.fullmatch(r"[A-Za-z0-9_]+", DB_NAME):
        raise ValueError(
            f"DB_NAME may only contain letters, digits and underscores: {DB_NAME!r}"
        )

    # Our database does not exist yet, so connect to the built-in "master" database.
    # CREATE DATABASE cannot run inside a transaction, which is why autocommit is on.
    connection = get_connection(database="master", autocommit=True)
    try:
        connection.execute(f"IF DB_ID('{DB_NAME}') IS NULL CREATE DATABASE [{DB_NAME}]")
    finally:
        connection.close()


def create_tables() -> None:
    """Run every step in sql/schema.sql against our database."""
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    # "GO" on its own line separates the steps. It is not SQL itself, so we split
    # the file on it and send the steps one at a time.
    steps = [
        step.strip()
        for step in re.split(r"^\s*GO\s*$", sql, flags=re.MULTILINE | re.IGNORECASE)
    ]

    connection = get_connection()
    try:
        for step in steps:
            if step:
                connection.execute(step)
        connection.commit()  # save all the steps together
    finally:
        connection.close()


def main() -> None:
    """The entry point for the "swo-setup-db" command."""
    create_database()
    create_tables()
    print(f"Database '{DB_NAME}' is ready.")


if __name__ == "__main__":
    main()
