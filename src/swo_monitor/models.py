"""The data shapes used across the project, and the notification status values."""

from dataclasses import dataclass
from datetime import date, datetime

# Values for the notification_status column of the companies table.
# They are named here once, so a typo cannot silently break the notifications.
STATUS_SEEDED = "SEEDED"  # already on the register at the first run, so no email
STATUS_PENDING = "PENDING"  # new company, email not sent yet
STATUS_SENT = "SENT"  # email sent


@dataclass
class ParsedOrder:
    """One Stop Work Order, cleaned up and ready to store."""

    nid: int  # the register's own ID for this order
    title: str
    order_type: str  # ORIGINAL / MODIFIED / CONDITION_NOTICE / OTHER
    company_name: str  # as written in the title
    # Simplified form of the name, used to match the same company across orders.
    normalised_name: str
    acn: str | None  # 9 digits, or None if the order does not show one
    address: str | None
    url: str
    issued_date: date | None  # the date on the order
    published_at: datetime  # when it was added to the register (UTC)
    revision_id: int  # changes each time the register edits the order


@dataclass
class Company:
    """A company that has had a Stop Work Order issued against it."""

    name: str
    normalised_name: str
    acn: str | None
    date_added: datetime
    # The database's ID for this company. None until the company has been saved.
    company_id: int | None = None
