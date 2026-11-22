# Stop Work Orders Monitor

This is a small Python tool that keeps an eye on the **Stop Work Orders** section of the NSW Building Commission's [Register of building work orders](https://www.nsw.gov.au/departments-and-agencies/building-commission/register-of-building-work-orders). Every time it runs, it:

1. fetches every Stop Work Order from the register,
2. stores the orders, and the companies they were issued to, in **SQL Server**,
3. sends an **email** for each company it hasn't seen before, with the company name, company number (ACN) and the date it was added.

## Quick start

### Prerequisites

| Tool | Why | Install |
|---|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Runs SQL Server and the test mail server | See link |
| [uv](https://docs.astral.sh/uv/) | Installs Python 3.13 and the dependencies | See link |
| Microsoft ODBC Driver 18 for SQL Server | Lets Python talk to SQL Server | Windows: `winget install Microsoft.msodbcsql.18`. Other systems: [Microsoft's instructions](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server) |

### Steps

**1. Start SQL Server and Mailpit.**

Mailpit is a fake email server. It accepts the email from the tool and then stops, so nothing ever reaches a real inbox. That makes it safe for testing.

The command below sets the database password to `Str0ngLocalPass`, which is also the default in the settings file, so you can copy both as they are. If you'd rather use your own, SQL Server wants at least 8 characters with upper case, lower case and a digit. If the password is too weak, the container starts and then stops again a few seconds later.

```
docker run -e "ACCEPT_EULA=Y" -e "MSSQL_SA_PASSWORD=Str0ngLocalPass" -p 1433:1433 --name sqlserver -d mcr.microsoft.com/mssql/server:2025-latest
docker run -d --name mailpit -p 1025:1025 -p 8025:8025 axllent/mailpit
```

Give SQL Server about 20 seconds to start. `docker ps` should show both containers as "Up".

**2. Create your settings file.** Copy `.env.example` to `.env`. The defaults work as they are. If you chose your own password in step 1, set `DB_PASSWORD` to match.

```
copy .env.example .env        (Windows)
cp .env.example .env          (macOS, Linux)
```

**3. Install the dependencies.**

```
uv sync
```

**4. Create the database and tables.** You only need to do this once, but it's safe to run again.

```
uv run swo-setup-db
```

**5. Run the monitor.**

```
uv run swo-monitor
```

The first run stores everything that is currently on the register and doesn't send any emails:

```
1. Fetched 11 orders from the register
2. Parsed 11 orders
3. Loaded 0 known companies
4. Matched orders to companies: 7 new
5. Saved 7 new companies as SEEDED, and 11 new orders
6. Companies to email about: 0 (mail server: localhost:1025)
```

If you run it again, it finds nothing new. Running it twice never creates duplicate rows or sends the same email again.

## See a notification arrive

New Stop Work Orders only show up about once a month, so you probably won't see a real one while testing. The easiest way to simulate one is to delete a company from the database and run the monitor again. The tool sees that company as new and sends the email.

```
docker exec sqlserver /opt/mssql-tools18/bin/sqlcmd -I -S localhost -U sa -P "Str0ngLocalPass" -C -d NSWBuildingTakeHome -Q "DELETE FROM dbo.stop_work_orders WHERE extracted_company_name LIKE 'Perry%'; DELETE FROM dbo.companies WHERE name LIKE 'Perry%';"

uv run swo-monitor --mailpit
```

Then open <http://localhost:8025> and you should see this:

```
Subject: New company on the Stop Work Orders register: Perry Properties Pty Ltd

Company name: Perry Properties Pty Ltd
Company number (ACN): 002635421
Date added: 21 April 2026
```

A few things worth knowing about those commands:

- `--mailpit` sends the email to Mailpit no matter what `.env` says, so a test can never send a real email by accident.
- `sqlcmd` needs the `-I` flag. The `companies` table uses filtered indexes, and SQL Server only lets you change a table like that when this setting is on.
- Pick a company that has only one order, like Perry Properties. If you delete one of Ausfield's three orders, no email is sent, because the tool still knows the company.

## Configuration

All the settings are environment variables, and for local use they are read from `.env`. [.env.example](.env.example) lists every one of them with a comment. The defaults match the commands in this README, so nothing needs changing for a local run. `.env` is never committed.

If you want the email to land in a real inbox, you point the same tool at a real mail server. It's a settings change, not a code change, because the tool uses standard SMTP. `.env.example` has a ready-made block for Gmail. I tested it both ways: with Mailpit, and with Gmail delivering to a real inbox.

## Tests

```
uv run pytest
```

There are 50 tests and they run in under a second. They use a saved copy of the real API response, so they don't need the network, the database or a mail server. They cover the parsing (including every ACN format I found on the register), the rule for matching orders to companies, the checks on the fetched data, and the wording of the email.

The database code and the actual sending of email aren't covered by automated tests. I tested those by hand, starting from fresh containers and following the steps above.

## How it works

`uv run swo-monitor` runs six steps. You can read them from top to bottom in [main.py](src/swo_monitor/main.py):

| Step | File | What happens |
|---|---|---|
| 1. Fetch | `fetch.py` | Calls the register's search API, page by page, then checks the results |
| 2. Parse | `parse.py` | Turns each raw record into a clean order: company name, ACN, order type, dates |
| 3. Load | `store.py` | Reads the companies that are already in the database |
| 4. Match | `matching.py` | Works out which company each order belongs to, and which companies are new |
| 5. Save | `store.py` | Inserts the new companies and orders, in one transaction |
| 6. Notify | `send_email.py` | Emails about each company that is still waiting for one, then marks it as sent |

The database setup (`uv run swo-setup-db`) is deliberately a separate command. Creating tables is a one-off job, and it needs more permissions than the daily run should have.

### Where the data comes from

The register page is built by JavaScript, so there are no orders in its HTML. The page gets them from a JSON search endpoint, and the tool calls that same endpoint directly:

```
POST https://www.nsw.gov.au/api/v1/elasticsearch/prod_content/_search
```

This means I don't need a headless browser, and JSON is a lot more stable to read than a page layout. I checked `robots.txt` and this path isn't disallowed. The tool makes one small request per run and identifies itself with a `User-Agent`.

One thing I learned while testing: a `200 OK` doesn't mean you got the right data. I accidentally sent a request with an empty body, and it still came back as 200, with ten unrelated news articles. So every run now checks two things: the number of results matches the total the API reports, and every record is actually in the Stop Work Orders category. If either check fails, or the network fails, the run stops and nothing is saved.

### The data model

There are two tables, defined in [schema.sql](sql/schema.sql). One company can have many orders, but an order belongs to only one company.

```
companies                         stop_work_orders
---------                         ----------------
company_id (PK)   1 -------- *    nid (PK)
name                              company_id (FK)
normalised_name                   title, order_type
acn                               extracted_company_name, extracted_acn
date_added                        address, url
notification_status               issued_date, published_at
notified_at                       revision_id
first_seen_at                     first_seen_at
```

- `stop_work_orders` has one row per entry on the register. Its primary key is `nid`, which is the register's own ID for the entry, so the same order can never be stored twice.
- `companies` has one row per company (or individual).

The task outline talks about a list of companies, but the register is really a list of orders, and one company can have several. Ausfield Investment has three. So I store the data the way the register has it, and work out the companies from that.

The database also enforces two rules on its own, as a safety net in case the code has a bug: no two companies can share an ACN, and no two companies without an ACN can share a name. Both are filtered unique indexes. A normal `UNIQUE` on the ACN column wouldn't work here, because SQL Server only allows one empty value in a unique column, and several companies have no ACN.

All times are stored in UTC and only converted to Sydney time when they are shown to someone.

### Deciding what counts as the same company

Everything about "is this a new company?" depends on this rule. It lives in [matching.py](src/swo_monitor/matching.py):

1. If the order has an ACN, look for a company with that ACN.
2. If not, look for a company with the same normalised name (lower case, no punctuation, no "Pty" or "Ltd").
3. If neither matches, it's a new company.

I use both the ACN and the name because neither one is enough by itself in the real data:

- The ACN is the better identifier. It is a company's legal identity, and it never changes. But the register doesn't always show it. Ausfield Investment has no ACN on any of its three orders, and Sustainable Homes Australia shows it on only two of its three.
- The name is always there, but it's less reliable. The same company appears as "R and D" on one order and "R And D" on another.

The Sustainable Homes order without an ACN is the best example of why both are needed. It has to match by name against a company that was created from an ACN. Otherwise it would be counted as an eighth company and a false email would go out.

Two more details. If a company is first seen without an ACN and a later order shows one, the ACN gets filled in. And if two orders have the same name but different ACNs, they are treated as two different companies.

I went with exact matching on the normalised name, not "fuzzy" matching. If the register misspells a name, the worst that happens is one extra email. Fuzzy matching could merge two different companies and hide a real alert, which is the worse mistake for a tool like this.

### Emails, and not sending them twice

Each run compares the register with the database. Any company that isn't already stored is new. Every company has a `notification_status`:

| Status | Meaning |
|---|---|
| `SEEDED` | Was already on the register at the first run, so no email |
| `PENDING` | New company, email not sent yet |
| `SENT` | Email sent |

A run emails every `PENDING` company and then marks it as `SENT`. If the email fails, the company stays `PENDING` and the next run tries again, so a mail outage doesn't lose a notification.

The email is sent first and marked as sent second. If a run stopped between those two steps, the next run would send that email again. I decided that a rare duplicate is better than a missed alert.

## Assumptions

Some parts of the task outline were left open. These are the calls I made.

| Question | What I decided |
|---|---|
| The task outline mentions "companies in liquidation" | I think this wording was carried over from a similar task, so I treated it as Stop Work Orders throughout |
| Does a new order trigger an email, or a new company? | A new company, which is what the task outline says. Another order for a company we already know sends nothing |
| What is the "company number"? | The ACN. It's the only identifier the register shows. If an order doesn't have one, the email says "Not provided" |
| What is the "date added"? | The date the register published the company's first order, shown in Sydney time. It's not the date the tool first noticed it, which could be days later |
| Should the first run email about everything already listed? | No. Those companies were on the register before the monitoring started |
| What about orders issued to an individual? | They are treated the same as companies, just without a company number |
| Do "Modified" orders and condition notices count? | Yes. Every entry in the category is stored with an `order_type`, and any of them can introduce a new company |

## How I approached the task

1. I started with the task outline and wrote down everything it left open. That list became the table above.
2. Before writing any code, I opened the register in the browser's developer tools to see what the page actually loads. That's how I found the JSON endpoint. I then checked with `curl` that it works outside of a browser, and read `robots.txt`.
3. I went through all 11 orders by hand. This is where the awkward cases came from: three different ACN formats, missing ACNs, an ABN sitting right next to an ACN, one company written two ways, and an order issued to an individual.
4. I designed the tables and the matching rule around those cases. Then I built each piece on its own (email, database connection, fetch, parse, match) and only joined them into one command once each piece worked.
5. I wrote tests against a saved copy of the real API response, and ran the whole thing by hand from fresh containers, including the simulated new company.

## Scheduling

The tool does one check and then exits. I left a scheduler out on purpose, because the operating system (or the hosting platform) is better at that job. New orders appear about once a month, so running it once a day is plenty. Running it more often doesn't hurt.

Windows (Task Scheduler):

```
schtasks /Create /TN "SWO Monitor" /SC DAILY /ST 08:00 /TR "cmd /c cd /d C:\path\to\project && uv run swo-monitor"
```

Linux or macOS (cron):

```
0 8 * * * cd /path/to/project && uv run swo-monitor
```

## What it doesn't do yet

- **Removed or edited orders.** An order is stored once, the first time it is seen. If the register edits or removes it later, the stored row doesn't change. The `revision_id` column holds the register's version number for the entry, which is what I would compare to detect an edit.
- **Another order for a company we already know.** This sends no email, because that's what the task outline asks for. I would add an option to email on every new order and say whether the company is new or a repeat.
- **Finding missing ACNs.** The ABN Lookup service could bridge a company's name to its real ACN, for the companies whose orders don't show one. I already have an API key for it from a personal project, so this is the first thing I would add.
- **Alerting when a run fails.** If the website changes or the database is down, the run stops with an error, but nobody is told. I would replace `print` with proper logging and send an alert.
- **Two runs at the same time.** The database constraints stop duplicate rows, but the second run would stop with an error.
- **Smaller things.** A Docker Compose file to start both containers with one command, and automated tests for the database code.

To deploy this on Azure, I'd add a Dockerfile for the app and run it as a scheduled container job, with Azure SQL Database for the data, Azure Communication Services for the email, and Key Vault for the secrets. The database login would be an account with only the permissions it needs, not `sa`.
