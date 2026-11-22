"""Tests for the checks on fetched data, and for the wording of the email.

Neither needs the network: check_orders works on a list, and the email is built
without being sent.
"""

from datetime import UTC, datetime

import pytest
from conftest import make_company

from swo_monitor.fetch import check_orders
from swo_monitor.models import Company
from swo_monitor.send_email import build_new_company_email

# --- check_orders: a "200 OK" is not proof of correct data ------------------


def test_the_saved_orders_pass_the_checks(raw_orders):
    check_orders(raw_orders, total=11)  # no error raised


def test_fewer_orders_than_the_api_reported_is_rejected(raw_orders):
    with pytest.raises(ValueError, match="reported 11"):
        check_orders(raw_orders[:5], total=11)


def test_a_record_that_is_not_a_stop_work_order_is_rejected(raw_orders):
    # What happened during testing: an empty request body returned unrelated articles.
    article = {"_id": "entity:node/1:en", "_source": {"name_category": ["News"]}}
    with pytest.raises(ValueError, match="not a Stop Work Order"):
        check_orders([*raw_orders[:10], article], total=11)


# --- The email --------------------------------------------------------------


def test_email_has_the_company_name_number_and_date_added():
    company = Company(
        name="Perry Properties Pty Ltd",
        normalised_name="perry properties",
        acn="002635421",
        date_added=datetime(2026, 4, 21, 2, 4, 38, tzinfo=UTC),
    )

    message = build_new_company_email(company)
    body = message.get_content()

    assert "Perry Properties Pty Ltd" in message["Subject"]
    assert "Company name: Perry Properties Pty Ltd" in body
    assert "Company number (ACN): 002635421" in body
    assert "Date added: 21 April 2026" in body


def test_email_says_not_provided_when_there_is_no_acn():
    body = build_new_company_email(make_company("Jianrong Song")).get_content()
    assert "Company number (ACN): Not provided" in body


def test_email_date_is_shown_in_sydney_time():
    # 11pm on 30 June in UTC is already 9am on 1 July in Sydney.
    company = make_company("Acme Pty Ltd")
    company.date_added = datetime(2026, 6, 30, 23, 0, tzinfo=UTC)

    body = build_new_company_email(company).get_content()

    assert "Date added: 1 July 2026" in body
