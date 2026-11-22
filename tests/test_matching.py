"""Tests for matching.py: which company an order belongs to, and which are new.

"New company" is what triggers an email, so these are the most important tests.
"""

import copy

from conftest import make_company, make_order

from swo_monitor.matching import find_matching_company, match_orders_to_companies

# --- The saved API response: 11 orders, 7 companies -------------------------


def test_first_run_finds_seven_companies_in_the_saved_orders(orders):
    results = match_orders_to_companies(orders, known_companies=[])

    assert sorted(company.name for company in results.new_companies) == [
        "Ausfield Investment Pty Ltd",
        "Jianrong Song",
        "Natoby Pty Ltd",
        "PSR Crownview Investment Pty Ltd",
        "Perry Properties Pty Ltd",
        "Richmond Rose Bay Pty Ltd",
        "Sustainable Homes Australia R And D Pty Ltd",
    ]
    assert len(results.company_for_order) == 11  # every order was given a company


def test_three_ausfield_orders_with_no_acn_become_one_company(orders):
    results = match_orders_to_companies(orders, known_companies=[])

    ausfield = [c for c in results.new_companies if c.name.startswith("Ausfield")]
    assert len(ausfield) == 1
    assert ausfield[0].acn is None
    ausfield_orders = [o for o in orders if o.company_name.startswith("Ausfield")]
    assert len(ausfield_orders) == 3
    assert all(results.company_for_order[o.nid] is ausfield[0] for o in ausfield_orders)


def test_the_sustainable_homes_order_without_an_acn_joins_the_same_company(orders):
    results = match_orders_to_companies(orders, known_companies=[])

    sustainable = [c for c in results.new_companies if c.name.startswith("Sustainable")]
    assert len(sustainable) == 1
    assert sustainable[0].acn == "647350187"
    their_orders = [o for o in orders if o.company_name.startswith("Sustainable")]
    assert len(their_orders) == 3


def test_a_company_takes_its_name_and_date_from_its_earliest_order(orders):
    results = match_orders_to_companies(orders, known_companies=[])

    sustainable = next(
        c for c in results.new_companies if c.name.startswith("Sustainable")
    )
    earliest = min(
        (o for o in orders if o.company_name.startswith("Sustainable")),
        key=lambda o: o.published_at,
    )
    assert sustainable.date_added == earliest.published_at
    assert sustainable.name == earliest.company_name


def test_a_second_run_with_the_same_orders_finds_nothing_new(orders):
    known = match_orders_to_companies(orders, known_companies=[]).new_companies

    results = match_orders_to_companies(orders, known_companies=copy.deepcopy(known))

    assert results.new_companies == []
    assert results.updated_companies == []
    assert len(results.company_for_order) == 11


def test_a_company_missing_from_the_known_list_is_reported_as_new(orders):
    # This is the demo: remove one company from the database, run again, get one email.
    known = match_orders_to_companies(orders, known_companies=[]).new_companies
    without_perry = [c for c in copy.deepcopy(known) if not c.name.startswith("Perry")]

    results = match_orders_to_companies(orders, known_companies=without_perry)

    assert [c.name for c in results.new_companies] == ["Perry Properties Pty Ltd"]


def test_the_known_list_passed_in_is_not_changed(orders):
    known = []
    match_orders_to_companies(orders, known_companies=known)
    assert known == []


# --- The matching rule, one case at a time ----------------------------------


def test_an_order_matches_a_company_with_the_same_acn_even_if_the_name_differs():
    acme = make_company("Acme Pty Ltd", acn="004085616")
    order = make_order(1, "Acme Renamed Pty Ltd", acn="004085616")

    assert find_matching_company(order, [acme]) is acme


def test_an_order_without_an_acn_matches_by_name():
    acme = make_company("Acme Pty Ltd", acn="004085616")
    order = make_order(1, "ACME PTY LTD", acn=None)

    assert find_matching_company(order, [acme]) is acme


def test_same_name_with_a_different_acn_is_a_different_company():
    acme = make_company("Acme Pty Ltd", acn="004085616")
    order = make_order(1, "Acme Pty Ltd", acn="647350187")

    assert find_matching_company(order, [acme]) is None

    results = match_orders_to_companies([order], [acme])
    assert [(c.name, c.acn) for c in results.new_companies] == [
        ("Acme Pty Ltd", "647350187")
    ]


def test_an_unknown_name_and_acn_is_a_new_company():
    acme = make_company("Acme Pty Ltd", acn="004085616")
    order = make_order(1, "Brand New Builders Pty Ltd", acn="647350187")

    assert find_matching_company(order, [acme]) is None


def test_a_company_known_only_by_name_gains_its_acn_from_a_later_order():
    acme = make_company("Acme Pty Ltd", acn=None)
    order = make_order(1, "Acme Pty Ltd", acn="004085616")

    results = match_orders_to_companies([order], [acme])

    assert results.new_companies == []  # no email: the company was already known
    assert results.updated_companies == [acme]
    assert acme.acn == "004085616"


def test_two_orders_for_one_new_company_in_the_same_run_create_it_once():
    first = make_order(1, "Acme Pty Ltd", acn=None, day=1)
    second = make_order(2, "Acme Pty Ltd", acn="004085616", day=2)

    results = match_orders_to_companies([second, first], known_companies=[])

    assert len(results.new_companies) == 1
    company = results.new_companies[0]
    assert company.acn == "004085616"  # picked up from the second order
    assert company.date_added == first.published_at  # from the earliest order
    assert results.updated_companies == []  # it is new, not "updated"
    assert results.company_for_order[1] is company
    assert results.company_for_order[2] is company
