"""Open connections to SQL Server.

Check the connection with:  uv run python -m swo_monitor.db
"""

import pyodbc

from swo_monitor import config


def get_connection(
    database: str = config.DB_NAME, autocommit: bool = False
) -> pyodbc.Connection:
    """Open a connection to SQL Server.

    database: which database to open. Use "master" before our own database exists.
    autocommit: True makes each statement save immediately. CREATE DATABASE needs this,
        because it cannot run inside a transaction.
    """
    if not config.DB_PASSWORD:
        raise ValueError(
            "DB_PASSWORD is not set. Add it to your .env file (see .env.example)."
        )

    # {{ and }} are literal braces in an f-string. ODBC wants the driver name in braces
    # because it contains spaces.
    connection_string = (
        f"DRIVER={{{config.DB_DRIVER}}};"
        f"SERVER={config.DB_SERVER};"
        f"DATABASE={database};"
        f"UID={config.DB_USER};"
        f"PWD={config.DB_PASSWORD};"
        # Driver 18 encrypts by default. The local container uses a self-signed
        # certificate, so we tell the driver to trust it. Production would use a real one.
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(connection_string, autocommit=autocommit, timeout=10)


if __name__ == "__main__":
    # Quick check: connect to the built-in "master" database and print the server version.
    connection = get_connection(database="master")
    try:
        version = connection.execute("SELECT @@VERSION").fetchone()[0]
        print("Connected to SQL Server:")
        print(version)
    finally:
        connection.close()
