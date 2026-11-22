"""Fetch the Stop Work Orders from the register's API.

Check it on its own with:  uv run python -m swo_monitor.fetch
"""

import requests

API_URL = "https://www.nsw.gov.au/api/v1/elasticsearch/prod_content/_search"

PAGE_SIZE = 50  # how many orders to ask for per request

# Tells the website who is calling, which is good manners for an automated client.
USER_AGENT = "stop-work-orders-monitor/0.1"

# Every result must carry this category. See check_orders below.
STOP_WORK_ORDERS_CATEGORY = "Stop work orders"


def fetch_data_from_api(page_size: int = PAGE_SIZE) -> list[dict]:
    """Fetch every Stop Work Order from the API and return them as a list.

    The API returns results in pages, meaning we may need to make multiple requests to
    get all the data. It has no "has more" flag. Instead, every response includes the
    total number of matching orders (hits.total.value), so we keep making requests
    until we have collected that many.

    Any problem (network error, error status, unexpected results) raises an error and
    stops the run. Returning a partial list would be worse: on an empty database it
    would look like a first run, and the missing companies would be emailed about later.
    """

    payload = {
        "query": {
            "bool": {
                "filter": [
                    {"term": {"type": "resource"}},
                    {"terms": {"agency_name": ["Building Commission NSW"]}},
                    {"terms": {"name_category": [STOP_WORK_ORDERS_CATEGORY]}},
                ]
            }
        },
        # Newest first. "nid" breaks ties between orders with the same date, so the
        # order of results is identical on every request and pages never overlap.
        "sort": [{"resource_date": "desc"}, {"nid": "asc"}],
        "from": 0,  # how many results to skip (changed for each page below)
        "size": page_size,  # how many results to return per page
    }

    # All orders are held in memory. That is fine at this size (about a dozen orders).
    orders = []

    while True:
        # "size" and "from" are the same idea as take/skip or limit/offset.
        # Skip the orders we already have, so this request returns the next page.
        payload["from"] = len(orders)

        response = requests.post(
            API_URL, json=payload, headers={"User-Agent": USER_AGENT}, timeout=10
        )

        # Raises an error if the status code is 4xx or 5xx (e.g. 404 or 500).
        # Without it, a failed request would carry on as if it had worked.
        response.raise_for_status()

        hits = response.json()["hits"]
        total = hits["total"]["value"]  # total matching orders, across all pages
        page = hits["hits"]  # the orders on this page
        orders.extend(page)

        # Stop when we have everything. The "not page" check stops an endless loop
        # if the API ever returns an empty page before we reach the total.
        if len(orders) >= total or not page:
            break

    check_orders(orders, total)
    return orders


def check_orders(orders: list[dict], total: int) -> None:
    """Make sure the API returned what we asked for. Raises ValueError if not.

    A "200 OK" status is not proof of correct data. While testing, a request with an
    empty body still returned 200, but with ten unrelated nsw.gov.au news articles.
    """
    if len(orders) != total:
        raise ValueError(f"The API reported {total} orders but returned {len(orders)}.")

    for order in orders:
        categories = order["_source"].get("name_category", [])
        if STOP_WORK_ORDERS_CATEGORY not in categories:
            raise ValueError(
                f"The API returned a record that is not a Stop Work Order: {order.get('_id')}"
            )


if __name__ == "__main__":
    # Quick check: fetch the orders and list their titles.
    fetched_orders = fetch_data_from_api()
    print(f"Fetched {len(fetched_orders)} orders")
    for order in fetched_orders:
        print(order["_source"]["nid"][0], order["_source"]["title"][0])
