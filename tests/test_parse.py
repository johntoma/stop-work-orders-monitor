"""Tests for parse.py: turning raw API records into clean orders."""

from datetime import UTC, date, datetime

import pytest

from swo_monitor.parse import (
    classify_order_type,
    extract_acn,
    extract_company_name,
    is_valid_acn,
    normalise_name,
    parse_order,
)

# --- Company name -----------------------------------------------------------


# parametrize runs the same test once per row, with the values filled in.
@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Stop Work Order for Perry Properties Pty Ltd", "Perry Properties Pty Ltd"),
        # lower-case "order", as the register wrote it for this company
        ("Stop Work order for Richmond Rose Bay Pty Ltd", "Richmond Rose Bay Pty Ltd"),
        ("Modified Stop Work Order for Natoby Pty Ltd", "Natoby Pty Ltd"),
        (
            "Notice of Imposition of a Condition Upon a Stop Work Order for Acme Pty Ltd",
            "Acme Pty Ltd",
        ),
        ("Stop Work Order for Jianrong Song", "Jianrong Song"),  # an individual
    ],
)
def test_company_name_is_the_text_after_order_for(title, expected):
    assert extract_company_name(title) == expected


def test_a_title_without_order_for_is_rejected():
    with pytest.raises(ValueError):
        extract_company_name("Building work rectification notice")


# --- Order type -------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Stop Work Order for X", "ORIGINAL"),
        ("Stop Work order for X", "ORIGINAL"),
        ("Modified Stop Work Order for X", "MODIFIED"),
        (
            "Notice of Imposition of a Condition Upon a Stop Work Order for X",
            "CONDITION_NOTICE",
        ),
        ("Revocation of an order for X", "OTHER"),  # wording we have not seen yet
    ],
)
def test_order_type_comes_from_the_start_of_the_title(title, expected):
    assert classify_order_type(title) == expected


# --- Name normalisation -----------------------------------------------------


def test_names_that_differ_only_in_letter_case_normalise_the_same():
    # The register writes this company both ways.
    assert normalise_name(
        "Sustainable Homes Australia R and D Pty Ltd"
    ) == normalise_name("Sustainable Homes Australia R And D Pty Ltd")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Perry Properties Pty Ltd", "perry properties"),
        ("PERRY PROPERTIES PTY. LIMITED", "perry properties"),
        ("The Richmond Rose-Bay Pty Ltd", "richmond rose bay"),
        ("Jianrong Song", "jianrong song"),
    ],
)
def test_normalise_ignores_case_punctuation_the_and_company_type_words(name, expected):
    assert normalise_name(name) == expected


def test_different_companies_do_not_normalise_the_same():
    assert normalise_name("Ausfield Investment Pty Ltd") != normalise_name(
        "Natoby Pty Ltd"
    )


# --- ACN --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ("<p>Sustainable Homes (ACN 647 350 187) (the Subject)</p>", "647350187"),
        (
            "<li>Perry Properties Pty Ltd (ACN 002635421)</li>",
            "002635421",
        ),  # leading zeros kept
        ("<li>Natoby Pty Ltd (A.C.N 601533519)</li>", "601533519"),
        (
            "<p>ACN&nbsp;601&nbsp;764&nbsp;578</p>",
            "601764578",
        ),  # HTML non-breaking spaces
    ],
)
def test_acn_is_found_in_each_format_the_register_uses(html, expected):
    assert extract_acn(html) == expected


def test_an_abn_is_not_mistaken_for_an_acn():
    html = (
        "<p>Richmond Rose Bay Pty Ltd (ACN 636 583 581) as trustee for "
        "The Richmond Rose Bay Unit Trust (ABN 27 184 210 983)</p>"
    )
    assert extract_acn(html) == "636583581"
    assert extract_acn("<p>The Unit Trust (ABN 27 184 210 983)</p>") is None


@pytest.mark.parametrize(
    "html", [None, "", "<p>Ausfield Investment Pty Ltd (the Developer)</p>"]
)
def test_no_acn_gives_none(html):
    assert extract_acn(html) is None


def test_an_acn_with_a_wrong_check_digit_is_treated_as_missing():
    # 647 350 187 is valid; changing the last digit breaks the check.
    assert extract_acn("<p>ACN 647 350 188</p>") is None


def test_acn_check_digit():
    assert is_valid_acn("647350187")
    assert is_valid_acn("002635421")
    assert not is_valid_acn("647350188")
    assert not is_valid_acn("12345")  # too short
    assert not is_valid_acn("64735018X")  # not all digits


# --- Whole records, using the saved API response ----------------------------


def test_all_eleven_saved_orders_parse(orders):
    assert len(orders) == 11
    assert len({order.nid for order in orders}) == 11  # every nid is different


def test_one_order_is_parsed_field_by_field(raw_orders):
    raw = next(hit for hit in raw_orders if hit["_source"]["nid"] == [117218])
    order = parse_order(raw)

    assert order.nid == 117218
    assert order.title == "Stop Work Order for Perry Properties Pty Ltd"
    assert order.order_type == "ORIGINAL"
    assert order.company_name == "Perry Properties Pty Ltd"
    assert order.normalised_name == "perry properties"
    assert order.acn == "002635421"
    assert (
        order.address == "43-51 Addison Road, Marrickville NSW 2204 Lot 101/ DP 1304727"
    )
    assert order.url == (
        "https://www.nsw.gov.au/departments-and-agencies/building-commission/"
        "register-of-building-work-orders/stop-work-order-for-perry-properties-pty-ltd"
    )
    assert order.issued_date == date(2026, 4, 20)
    assert order.published_at == datetime(2026, 4, 21, 2, 4, 38, tzinfo=UTC)
    assert order.revision_id == 20616260


def test_orders_without_an_acn_in_the_saved_data(orders):
    without_acn = sorted(order.company_name for order in orders if order.acn is None)
    assert (
        without_acn
        == [
            "Ausfield Investment Pty Ltd",
            "Ausfield Investment Pty Ltd",
            "Ausfield Investment Pty Ltd",
            "Jianrong Song",
            "Sustainable Homes Australia R and D Pty Ltd",  # its other two orders do show the ACN
        ]
    )


def test_a_record_missing_a_required_field_is_rejected(raw_orders):
    broken = {"_source": dict(raw_orders[0]["_source"])}
    del broken["_source"]["nid"]
    with pytest.raises(ValueError, match="nid"):
        parse_order(broken)
