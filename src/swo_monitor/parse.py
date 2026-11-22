"""Turn raw API records into clean ParsedOrder objects.

Every function here is "pure": it takes values in and returns values out, with no
network or database access. That makes each one easy to test on its own.
"""

import html
import re
from datetime import UTC, datetime

from swo_monitor.models import ParsedOrder

BASE_URL = "https://www.nsw.gov.au"

# How company names are compared (see normalise_name below):
# the register writes the same company in different ways, e.g. "R and D" and "R And D",
# so two names count as the same when they match after ignoring letter case,
# punctuation, a leading "the", and the company-type words listed here.
# This is only the fallback. When an order shows an ACN, the ACN decides.
COMPANY_TYPE_WORDS = {"pty", "ltd", "limited", "proprietary"}


def get_field(source: dict, field: str, required: bool = True):
    """Return one field from an API record.

    The API wraps every value in a list, e.g. "nid": [117218], so we take the first item.
    """
    values = source.get(field)
    if values:
        return values[0]
    if required:
        raise ValueError(f"API record is missing the required field '{field}'")
    return None


def extract_company_name(title: str) -> str:
    """Return the text after "order for" in the title.

    "Modified Stop Work Order for Natoby Pty Ltd" -> "Natoby Pty Ltd"
    """
    match = re.search(r"order\s+for\s+(.+)", title, flags=re.IGNORECASE)
    if not match:
        raise ValueError(f"Could not find a company name in the title: {title!r}")
    return match.group(1).strip()


def classify_order_type(title: str) -> str:
    """Work out the kind of entry from the start of its title."""
    lowered = title.strip().lower()
    if lowered.startswith("modified"):
        return "MODIFIED"
    if lowered.startswith("notice of imposition"):
        return "CONDITION_NOTICE"
    if lowered.startswith("stop work order"):
        return "ORIGINAL"
    return "OTHER"


def normalise_name(name: str) -> str:
    """Simplify a name so that small differences in writing do not matter.

    "Sustainable Homes Australia R And D Pty Ltd" -> "sustainable homes australia r and d"

    Loosely follows how ASIC decides whether two company names are identical:
    ignore letter case, punctuation, a leading "the", and company-type words.
    """
    text = name.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)  # punctuation becomes a space
    words = text.split()
    if words and words[0] == "the":
        words = words[1:]
    kept = [word for word in words if word not in COMPANY_TYPE_WORDS]
    # If nothing is left (a name made only of ignored words), keep the words as they were.
    return " ".join(kept or words)


def is_valid_acn(acn: str) -> bool:
    """Check an ACN using ASIC's check-digit rule.

    The first 8 digits are multiplied by the weights 8, 7, 6, 5, 4, 3, 2, 1 and added up.
    The 9th digit must equal (10 - total % 10) % 10. This catches typing mistakes.
    """
    if len(acn) != 9 or not acn.isdigit():
        return False
    total = sum(int(digit) * weight for digit, weight in zip(acn[:8], range(8, 0, -1)))
    return (10 - total % 10) % 10 == int(acn[8])


def extract_acn(html_content: str | None) -> str | None:
    """Find the ACN in an order's HTML summary. Returns 9 digits, or None.

    Handles "ACN 647 350 187", "ACN 002635421" and "A.C.N 601533519".
    An ABN is not picked up, because the digits must directly follow the letters "ACN".
    """
    if not html_content:
        return None

    text = re.sub(r"<[^>]+>", " ", html_content)  # remove HTML tags
    text = html.unescape(text)  # "&amp;" -> "&", "&nbsp;" -> a non-breaking space
    text = text.replace("\xa0", " ")  # non-breaking space -> normal space

    # "A", "C", "N" with optional dots, then 9 digits that may have spaces between them.
    # (?!\d) means "not followed by another digit", so longer numbers are not cut short.
    match = re.search(
        r"\bA\.?C\.?N\.?\s*:?\s*((?:\d\s?){9})(?!\d)", text, flags=re.IGNORECASE
    )
    if not match:
        return None

    acn = re.sub(r"\s", "", match.group(1))
    # A number that fails the check is treated as "no ACN", so matching falls back to the name.
    return acn if is_valid_acn(acn) else None


def parse_order(hit: dict) -> ParsedOrder:
    """Convert one raw API result (a "hit") into a ParsedOrder."""
    source = hit["_source"]

    title = get_field(source, "title")
    company_name = extract_company_name(title)
    issued_epoch = get_field(source, "display_date", required=False)

    return ParsedOrder(
        nid=int(get_field(source, "nid")),
        title=title,
        order_type=classify_order_type(title),
        company_name=company_name,
        normalised_name=normalise_name(company_name),
        acn=extract_acn(get_field(source, "html_content", required=False)),
        address=get_field(source, "summary", required=False),
        url=BASE_URL + get_field(source, "url"),
        # The API gives dates as "epoch seconds": seconds since 1 Jan 1970, in UTC.
        issued_date=(
            datetime.fromtimestamp(issued_epoch, tz=UTC).date()
            if issued_epoch is not None
            else None
        ),
        published_at=datetime.fromtimestamp(get_field(source, "utc_created"), tz=UTC),
        revision_id=int(get_field(source, "vid")),
    )


def parse_orders(hits: list[dict]) -> list[ParsedOrder]:
    """Convert every raw API result into a ParsedOrder."""
    return [parse_order(hit) for hit in hits]
