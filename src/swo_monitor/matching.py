"""Work out which company each order belongs to, and which companies are new.

Nothing here touches the network or the database. The companies we already know
about are passed in as a list, so this logic can be tested with plain data.
"""

from dataclasses import dataclass, field

from swo_monitor.models import Company, ParsedOrder


@dataclass
class MatchResults:
    """What came out of matching a batch of orders against the known companies."""

    # Companies seen for the first time. These are the ones that trigger an email.
    new_companies: list[Company] = field(default_factory=list)
    # Known companies that had no ACN before, and gained one from a later order.
    updated_companies: list[Company] = field(default_factory=list)
    # Which company each order belongs to, keyed by the order's nid.
    company_for_order: dict[int, Company] = field(default_factory=dict)


def create_company_from_parsed_order(parsed_order: ParsedOrder) -> Company:
    """Create a new company from the first order we see for it."""
    return Company(
        name=parsed_order.company_name,
        normalised_name=parsed_order.normalised_name,
        acn=parsed_order.acn,
        date_added=parsed_order.published_at,
    )


def find_matching_company(
    order: ParsedOrder, companies: list[Company]
) -> Company | None:
    """Return the company this order belongs to, or None if it is a new company.

    The ACN is a company's legal identity, so it is checked first. Some orders do not
    show an ACN, so the normalised name is the fallback.
    """
    # 1. If the order has an ACN, look for a company with that ACN.
    if order.acn:
        for company in companies:
            if company.acn == order.acn:
                return company

    # 2. Otherwise, look for a company with the same normalised name.
    for company in companies:
        if company.normalised_name != order.normalised_name:
            continue
        # Same name but two different ACNs means two different companies
        # (for example, a name reused after the first company was deregistered).
        if order.acn and company.acn and order.acn != company.acn:
            continue
        return company

    # 3. No match: this is a company we have not seen before.
    return None


def match_orders_to_companies(
    orders: list[ParsedOrder], known_companies: list[Company]
) -> MatchResults:
    """Match every order to a company, creating companies that do not exist yet.

    known_companies: the companies already stored. An empty list on the first run.
    The list itself is not changed, but a known company that gains an ACN is updated.
    """
    result = MatchResults()
    companies = list(known_companies)  # a copy, so new companies can be added to it

    # Oldest first, so a company's name and date_added come from its earliest order.
    # nid breaks ties between orders published at the same moment.
    for order in sorted(orders, key=lambda o: (o.published_at, o.nid)):
        company = find_matching_company(order, companies)

        if company is None:
            company = create_company_from_parsed_order(order)
            companies.append(company)  # so later orders in this batch can match it
            result.new_companies.append(company)
        elif order.acn and not company.acn:
            # We knew this company by name only. This order reveals its ACN.
            company.acn = order.acn
            if company not in result.new_companies:
                result.updated_companies.append(company)

        result.company_for_order[order.nid] = company

    return result
