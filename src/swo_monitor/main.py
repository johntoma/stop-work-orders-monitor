"""Stop Work Orders monitor: the one command that runs everything.

Run it with:  uv run swo-monitor
         or:  uv run swo-monitor --mailpit   (send emails to the local test mail server,
                                              whatever the mail settings in .env say)

The flow, top to bottom:
    1. Fetch   - get every Stop Work Order from the register's API
    2. Parse   - turn each raw record into a clean ParsedOrder
    3. Load    - read the companies we already know about from the database
    4. Match   - work out which company each order belongs to, and which are new
    5. Save    - store the new companies and orders
    6. Notify  - email about each new company, then record that it was sent
"""

import argparse
from typing import Literal

from swo_monitor import config, send_email
from swo_monitor.db import get_connection
from swo_monitor.fetch import fetch_data_from_api
from swo_monitor.matching import MatchResults, match_orders_to_companies
from swo_monitor.models import Company, ParsedOrder
from swo_monitor.parse import parse_orders
from swo_monitor.store import (
    load_known_companies,
    load_pending_companies,
    mark_company_notified,
    save_results,
)


def run() -> None:
    """Run the whole pipeline once."""
    # 1. Fetch: raw records from the API, one per order.
    raw_orders = fetch_data_from_api()
    print(f"1. Fetched {len(raw_orders)} orders from the register")

    # 2. Parse: clean records with company name, ACN, order type and dates.
    orders: list[ParsedOrder] = parse_orders(raw_orders)
    print(f"2. Parsed {len(orders)} orders")

    # One database connection is shared by steps 3, 5 and 6.
    # try/finally closes it even if a step fails.
    connection = get_connection()
    try:
        # 3. Load: the companies already in the database.
        known_companies: list[Company] = load_known_companies(connection)
        print(f"3. Loaded {len(known_companies)} known companies")

        # An empty companies table means this is the first run. Everything on the register
        # was there before monitoring began, so it is stored without sending any emails.
        is_first_run: bool = len(known_companies) == 0

        # 4. Match: ACN first, normalised name as the fallback.
        results: MatchResults = match_orders_to_companies(orders, known_companies)
        print(f"4. Matched orders to companies: {len(results.new_companies)} new")
        for company in results.new_companies:
            print(f"     new: {company.name} (ACN: {company.acn or 'Not provided'})")

        # 5. Save: new companies start as SEEDED on the first run (no email),
        #    and as PENDING on later runs (email still to send).
        new_company_status: Literal["PENDING", "SEEDED"] = (
            "SEEDED" if is_first_run else "PENDING"
        )
        orders_added = save_results(connection, orders, results, new_company_status)
        # Commit makes the changes permanent. Until this line, a failure undoes all of them.
        connection.commit()
        print(
            f"5. Saved {len(results.new_companies)} new companies as {new_company_status}, "
            f"and {orders_added} new orders"
        )

        # 6. Notify: send first, then mark as sent. If the run stops between the two,
        #    the worst case is a repeated email next time, never a missed one.
        pending_companies: list[Company] = load_pending_companies(connection)
        print(
            f"6. Companies to email about: {len(pending_companies)} "
            f"(mail server: {config.SMTP_HOST}:{config.SMTP_PORT})"
        )
        for company in pending_companies:
            if send_email.send_new_company_email(company):
                mark_company_notified(connection, company)
                # Commit after each email, so one that was sent is never sent again
                # because a later one failed.
                connection.commit()
                print(f"     emailed: {company.name}")
            # If sending failed, the company stays PENDING and is retried on the next run.
    finally:
        connection.close()


def cli() -> None:
    """The entry point for the "swo-monitor" command (see [project.scripts] in pyproject.toml)."""
    # argparse reads the options typed after the command name.
    parser = argparse.ArgumentParser(
        prog="swo-monitor", description="Stop Work Orders monitor"
    )
    parser.add_argument(
        "--mailpit",
        action="store_true",  # the flag takes no value: present means True
        help="send emails to Mailpit (the local test mail server) instead of the server in .env",
    )
    arguments = parser.parse_args()

    if arguments.mailpit:
        send_email.use_mailpit()

    run()


if __name__ == "__main__":
    cli()
