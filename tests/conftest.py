"""Shared test data. pytest loads this file automatically.

A "fixture" is a named piece of test data. A test receives one by listing its name
as a parameter, e.g. def test_something(raw_orders): ...
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from swo_monitor.models import Company, ParsedOrder
from swo_monitor.parse import normalise_name, parse_orders

# A saved copy of the real API response (11 orders, captured 21 Nov 2026),
# so the tests never call the live website.
FIXTURE_FILE = Path(__file__).parent / "fixtures" / "stop_work_orders.json"


@pytest.fixture
def raw_orders() -> list[dict]:
    """The 11 orders exactly as the API returned them."""
    response = json.loads(FIXTURE_FILE.read_text(encoding="utf-8"))
    return response["hits"]["hits"]


@pytest.fixture
def orders(raw_orders) -> list[ParsedOrder]:
    """The same 11 orders after parsing."""
    return parse_orders(raw_orders)


def make_order(
    nid: int, name: str, acn: str | None = None, day: int = 1
) -> ParsedOrder:
    """Build a made-up order for a test. Only the fields that matching uses matter."""
    return ParsedOrder(
        nid=nid,
        title=f"Stop Work Order for {name}",
        order_type="ORIGINAL",
        company_name=name,
        normalised_name=normalise_name(name),
        acn=acn,
        address=None,
        url="https://example.com/order",
        issued_date=None,
        published_at=datetime(2026, 1, day, tzinfo=UTC),
        revision_id=1,
    )


def make_company(name: str, acn: str | None = None) -> Company:
    """Build a made-up company that is "already known"."""
    return Company(
        name=name,
        normalised_name=normalise_name(name),
        acn=acn,
        date_added=datetime(2025, 1, 1, tzinfo=UTC),
    )
