-- Tables for the Stop Work Orders monitor (SQL Server).
--
-- Run it with:  uv run swo-setup-db
-- It is safe to run more than once: each step first checks whether it is already done.
-- "GO" on its own line separates the steps, the same way SSMS and sqlcmd read it.
--
-- Conventions:
--   * All times are stored in UTC.
--   * Statuses are text, not true/false, so a new status can be added later.

-- One row per company (or individual) that has received a Stop Work Order.
IF OBJECT_ID('dbo.companies', 'U') IS NULL
CREATE TABLE dbo.companies (
    company_id          INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_companies PRIMARY KEY,
    name                NVARCHAR(200)     NOT NULL,  -- as written on the company's first order
    normalised_name     NVARCHAR(200)     NOT NULL,  -- simplified name, used for matching
    acn                 CHAR(9)           NULL,      -- digits only; NULL when no order shows one
    date_added          DATETIME2(0)      NOT NULL,  -- when the first order was published
    notification_status VARCHAR(20)       NOT NULL,  -- PENDING / SENT / SEEDED
    notified_at         DATETIME2(0)      NULL,      -- when the email was sent
    first_seen_at       DATETIME2(0)      NOT NULL   -- when this tool first stored the company
        CONSTRAINT DF_companies_first_seen_at DEFAULT SYSUTCDATETIME()
);
GO

-- No two companies may share an ACN.
-- A plain UNIQUE would allow only one row with no ACN, so the index skips those rows.
IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'UX_companies_acn' AND object_id = OBJECT_ID('dbo.companies'))
CREATE UNIQUE INDEX UX_companies_acn
    ON dbo.companies (acn)
    WHERE acn IS NOT NULL;
GO

-- No two companies WITHOUT an ACN may share a name.
IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'UX_companies_name_without_acn' AND object_id = OBJECT_ID('dbo.companies'))
CREATE UNIQUE INDEX UX_companies_name_without_acn
    ON dbo.companies (normalised_name)
    WHERE acn IS NULL;
GO

-- One row per entry on the register.
IF OBJECT_ID('dbo.stop_work_orders', 'U') IS NULL
CREATE TABLE dbo.stop_work_orders (
    nid                    INT            NOT NULL CONSTRAINT PK_stop_work_orders PRIMARY KEY,  -- the register's own ID
    company_id             INT            NOT NULL
        CONSTRAINT FK_stop_work_orders_companies REFERENCES dbo.companies (company_id),
    title                  NVARCHAR(500)  NOT NULL,
    order_type             VARCHAR(20)    NOT NULL,  -- ORIGINAL / MODIFIED / CONDITION_NOTICE / OTHER
    extracted_company_name NVARCHAR(200)  NOT NULL,  -- the name as this order wrote it
    extracted_acn          CHAR(9)        NULL,      -- the ACN as this order showed it
    address                NVARCHAR(500)  NULL,
    url                    NVARCHAR(500)  NOT NULL,
    issued_date            DATE           NULL,      -- the date on the order
    published_at           DATETIME2(0)   NOT NULL,  -- when the register published it
    revision_id            INT            NOT NULL,  -- changes when the register edits the order
    register_status        VARCHAR(20)    NOT NULL   -- LISTED / REMOVED
        CONSTRAINT DF_stop_work_orders_register_status DEFAULT 'LISTED',
    first_seen_at          DATETIME2(0)   NOT NULL
        CONSTRAINT DF_stop_work_orders_first_seen_at DEFAULT SYSUTCDATETIME(),
    last_seen_at           DATETIME2(0)   NOT NULL
        CONSTRAINT DF_stop_work_orders_last_seen_at DEFAULT SYSUTCDATETIME(),
    raw_json               NVARCHAR(MAX)  NULL       -- the full API record, for reprocessing
);
GO

-- Speeds up "all orders for this company".
IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'IX_stop_work_orders_company_id' AND object_id = OBJECT_ID('dbo.stop_work_orders'))
CREATE INDEX IX_stop_work_orders_company_id
    ON dbo.stop_work_orders (company_id);
GO
