"""Send the "new company" notification email over SMTP.

Send a test email with:  uv run python -m swo_monitor.send_email
"""

import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from swo_monitor import config
from swo_monitor.models import Company


def use_mailpit() -> None:
    """Ignore the mail settings in .env and send to Mailpit, the local test mail server.

    Used by the --mailpit flag of the swo-monitor command, so a test run cannot send a real email.
    """
    config.SMTP_HOST = "localhost"
    config.SMTP_PORT = 1025
    config.SMTP_SECURITY = "NONE"
    config.SMTP_USERNAME = ""
    config.SMTP_PASSWORD = ""


REGISTER_URL = (
    "https://www.nsw.gov.au/departments-and-agencies/building-commission/"
    "register-of-building-work-orders"
)

# Times are stored in UTC and shown to readers in Sydney time.
SYDNEY = ZoneInfo("Australia/Sydney")


def build_new_company_email(company: Company) -> EmailMessage:
    """Create the email for a new company. Building it is separate from sending it,
    so the wording can be checked without a mail server."""
    added = company.date_added.astimezone(SYDNEY)
    date_added_text = f"{added.day} {added:%B %Y}"  # e.g. "21 April 2026"

    message = EmailMessage()
    message["From"] = config.EMAIL_FROM
    message["To"] = config.EMAIL_TO
    message["Subject"] = f"New company on the Stop Work Orders register: {company.name}"
    message.set_content(
        "A new company has been added to the Stop Work Orders list on the "
        "NSW Building Commission's Register of building work orders.\n"
        "\n"
        f"Company name: {company.name}\n"
        f"Company number (ACN): {company.acn or 'Not provided'}\n"
        f"Date added: {date_added_text}\n"
        "\n"
        f"Register: {REGISTER_URL}\n"
    )
    return message


def send_email(message: EmailMessage) -> None:
    """Hand one email to the mail server. Raises an error if anything goes wrong."""
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=10) as server:
        # Real servers require an encrypted connection before login. Mailpit does not support it.
        if config.SMTP_SECURITY == "STARTTLS":
            server.starttls()

        # Real servers require a login. Mailpit accepts mail from anyone.
        if config.SMTP_USERNAME:
            server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)

        server.send_message(message)


def send_new_company_email(company: Company) -> bool:
    """Send the notification for one company. Returns True if sent, False if it failed.

    A failure is reported, not raised, so one bad send does not stop the run. The
    company stays PENDING in the database and is retried on the next run.
    """
    try:
        send_email(build_new_company_email(company))
    except (smtplib.SMTPException, OSError) as error:
        # SMTPException: the server refused (e.g. wrong password).
        # OSError: the server could not be reached (e.g. it is not running).
        print(f"   Email for {company.name} failed: {error}")
        return False
    return True


if __name__ == "__main__":
    # Send a sample email, to check the mail settings.
    sample = Company(
        name="Example Builders Pty Ltd",
        normalised_name="example builders",
        acn="004085616",
        date_added=datetime.now(UTC),
    )
    if send_new_company_email(sample):
        print(
            f"Test email sent to {config.EMAIL_TO} via {config.SMTP_HOST}:{config.SMTP_PORT}"
        )
