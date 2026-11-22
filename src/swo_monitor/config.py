"""Every setting for the project, in one place.

Values come from environment variables. For local use they are read from the .env
file in the project's top folder (see .env.example). A real environment variable always
wins over the file, which is how settings would be supplied in production.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# This file is at <project>/src/swo_monitor/config.py, so the project's top folder
# is two levels above the folder this file is in.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(ENV_FILE)  # does nothing if the file does not exist

SCHEMA_FILE = PROJECT_ROOT / "sql" / "schema.sql"

# --- Database (SQL Server) ---
DB_DRIVER = os.environ.get("DB_DRIVER", "ODBC Driver 18 for SQL Server")
DB_SERVER = os.environ.get(
    "DB_SERVER", "localhost,1433"
)  # host,port (SQL Server uses a comma)
DB_NAME = os.environ.get("DB_NAME", "NSWBuildingTakeHome")
DB_USER = os.environ.get("DB_USER", "sa")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")  # no default: it must be set in .env

# --- Email (SMTP) ---
# The defaults point at Mailpit, the local test mail server.
SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "1025"))
SMTP_SECURITY = os.environ.get("SMTP_SECURITY", "NONE").upper()  # NONE or STARTTLS
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "swo-monitor@example.com")
EMAIL_TO = os.environ.get("EMAIL_TO", "recipient@example.com")

# Stop straight away on a typo, so encryption cannot be switched off by accident.
if SMTP_SECURITY not in ("NONE", "STARTTLS"):
    raise ValueError(f"SMTP_SECURITY must be NONE or STARTTLS, not {SMTP_SECURITY!r}")
