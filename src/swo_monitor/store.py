"""Read and write companies and orders in the database.

This is the only file that contains SQL for the two tables.
"""

from datetime import UTC, datetime

import pyodbc

from swo_monitor.matching import MatchResults
from swo_monitor.models import STATUS_SENT, Company, ParsedOrder


def from_db_time(value: datetime) -> datetime:
    """Times in the database are UTC but carry no timezone label, so add the label back."""
    return value.replace(tzinfo=UTC)


def to_db_time(value: datetime) -> datetime:
    """The opposite of from_db_time: make sure the time is UTC, then remove the label."""
    return value.astimezone(UTC).replace(tzinfo=None)


def load_known_companies(
    connection: pyodbc.Connection, notification_status: str | None = None
) -> list[Company]:
    """Return the companies stored in the database. An empty list on the first run.

    notification_status: if given, return only the companies with that status,
        e.g. "PENDING" for the ones still waiting for an email.
    """
    sql = "SELECT company_id, name, normalised_name, acn, date_added FROM dbo.companies"
    parameters = []
    if notification_status is not None:
        sql += " WHERE notification_status = ?"
        parameters.append(notification_status)
    sql += " ORDER BY company_id"

    rows = connection.execute(sql, parameters)
    # pyodbc lets us read each column by name, e.g. row.name.
    return [
        Company(
            company_id=row.company_id,
            name=row.name,
            normalised_name=row.normalised_name,
            acn=row.acn,  # None when the database value is NULL
            date_added=from_db_time(row.date_added),
        )
        for row in rows
    ]


def save_results(
    connection: pyodbc.Connection,
    orders: list[ParsedOrder],
    results: MatchResults,
    new_company_status: str,
) -> int:
    """Store the outcome of a run. Returns how many orders were added.

    Every query uses "?" placeholders, so values travel separately from the SQL text.
    That is what prevents SQL injection.

    This function does not commit. The caller commits once at the end, so everything
    from one run is saved together, or not at all if something fails part-way.
    """
    # 1. Insert the new companies.
    #    OUTPUT INSERTED.company_id hands back the ID the database generated,
    #    which the orders in step 3 need.
    for company in results.new_companies:
        row = connection.execute(
            """
            INSERT INTO dbo.companies (name, normalised_name, acn, date_added, notification_status)
            OUTPUT INSERTED.company_id
            VALUES (?, ?, ?, ?, ?)
            """,
            company.name,
            company.normalised_name,
            company.acn,
            to_db_time(company.date_added),
            new_company_status,
        ).fetchone()
        company.company_id = row.company_id

    # 2. Fill in the ACN on known companies that did not have one before.
    for company in results.updated_companies:
        connection.execute(
            "UPDATE dbo.companies SET acn = ? WHERE company_id = ?",
            company.acn,
            company.company_id,
        )

    # 3. Insert the orders that are not stored yet.
    #    nid is the register's own ID, so it tells us which orders we already have.
    stored_nids = {
        row.nid for row in connection.execute("SELECT nid FROM dbo.stop_work_orders")
    }
    orders_added = 0
    for order in orders:
        if order.nid in stored_nids:
            continue
        company = results.company_for_order[order.nid]
        connection.execute(
            """
            INSERT INTO dbo.stop_work_orders
                (nid, company_id, title, order_type, extracted_company_name, extracted_acn,
                 address, url, issued_date, published_at, revision_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            order.nid,
            company.company_id,
            order.title,
            order.order_type,
            order.company_name,
            order.acn,
            order.address,
            order.url,
            order.issued_date,
            to_db_time(order.published_at),
            order.revision_id,
        )
        orders_added += 1

    return orders_added


def mark_company_notified(connection: pyodbc.Connection, company: Company) -> None:
    """Record that the email for this company was sent. Does not commit."""
    connection.execute(
        "UPDATE dbo.companies "
        "SET notification_status = ?, notified_at = SYSUTCDATETIME() "
        "WHERE company_id = ?",
        STATUS_SENT,
        company.company_id,
    )
