-- 006_asset_tracking.sql
-- Asset tracking schema: instruments (security master), holdings (per-account positions),
-- holding values, asset prices, classifications, sources, and documents for idempotent imports.

BEGIN;

-- Asset classes (taxonomy for categorizing instruments)
-- Note: ETFs are vehicles, not classes; use sub_class like "US equity", "intl equity", etc.
CREATE TABLE IF NOT EXISTS asset_classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    main_class TEXT NOT NULL,  -- equities, bonds, alternatives, cash, other
    sub_class TEXT NOT NULL,   -- US equity, intl equity, treasury, muni, etc.
    vehicle_type_default TEXT, -- stock, ETF, mutual_fund, bond, MMF, etc.
    metadata TEXT,             -- JSON for extensibility
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (json_valid(metadata) OR metadata IS NULL),
    UNIQUE(main_class, sub_class)
);

-- Asset sources (brokers, APIs, manual entry)
-- priority: lower = higher precedence (statement=1, manual=2, api=3)
CREATE TABLE IF NOT EXISTS asset_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,         -- e.g., "UBS Statement", "Schwab API", "Manual Entry"
    source_type TEXT NOT NULL,          -- statement, upload, api, manual
    priority INTEGER NOT NULL DEFAULT 2,
    contact_url TEXT,
    metadata TEXT,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (json_valid(metadata) OR metadata IS NULL),
    CHECK (source_type IN ('statement', 'upload', 'api', 'manual'))
);

-- Documents (for idempotent re-imports via document_hash)
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_hash TEXT NOT NULL UNIQUE, -- SHA256 of original file
    source_id INTEGER NOT NULL,
    broker TEXT,                        -- broker name for context
    period_end_date DATE,               -- statement period end date
    file_path TEXT,                     -- original file path (for reference only)
    metadata TEXT,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES asset_sources(id) ON DELETE RESTRICT,
    CHECK (json_valid(metadata) OR metadata IS NULL)
);

-- Instruments (security master - global securities with identifiers)
CREATE TABLE IF NOT EXISTS instruments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                 -- e.g., "Apple Inc", "Vanguard S&P 500 ETF"
    symbol TEXT,                        -- ticker symbol, e.g., "AAPL", "VOO"
    exchange TEXT,                      -- e.g., "NYSE", "NASDAQ", NULL for funds
    currency TEXT NOT NULL DEFAULT 'USD',
    vehicle_type TEXT,                  -- stock, ETF, mutual_fund, bond, MMF, fund_LP, note, option, crypto
    identifiers TEXT,                   -- JSON: {cusip, isin, sedol, figi, fund_id}
    metadata TEXT,                      -- JSON for broker-specific data, aliases
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (json_valid(identifiers) OR identifiers IS NULL),
    CHECK (json_valid(metadata) OR metadata IS NULL),
    CHECK (LENGTH(currency) = 3),
    CHECK (vehicle_type IN ('stock', 'ETF', 'mutual_fund', 'bond', 'MMF', 'fund_LP', 'note', 'option', 'crypto') OR vehicle_type IS NULL)
);

-- Unique index on symbol+exchange when both present
CREATE UNIQUE INDEX IF NOT EXISTS idx_instruments_symbol_exchange
    ON instruments(symbol, exchange)
    WHERE symbol IS NOT NULL AND exchange IS NOT NULL;

-- Holdings (per-account positions referencing instruments)
CREATE TABLE IF NOT EXISTS holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    instrument_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',  -- active, closed
    opened_at DATE,
    closed_at DATE,
    cost_basis_total REAL,              -- total cost basis in valuation currency
    cost_basis_per_unit REAL,           -- cost per share/unit
    cost_basis_method TEXT,             -- FIFO, LIFO, Specific, Avg
    position_side TEXT NOT NULL DEFAULT 'long',  -- long, short
    metadata TEXT,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
    FOREIGN KEY (instrument_id) REFERENCES instruments(id) ON DELETE RESTRICT,
    CHECK (json_valid(metadata) OR metadata IS NULL),
    CHECK (status IN ('active', 'closed')),
    CHECK (position_side IN ('long', 'short')),
    CHECK (cost_basis_method IN ('FIFO', 'LIFO', 'Specific', 'Avg') OR cost_basis_method IS NULL)
);

-- Unique index: one active holding per account+instrument
CREATE UNIQUE INDEX IF NOT EXISTS idx_holdings_account_instrument_active
    ON holdings(account_id, instrument_id)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_holdings_account ON holdings(account_id);
CREATE INDEX IF NOT EXISTS idx_holdings_instrument ON holdings(instrument_id);
CREATE INDEX IF NOT EXISTS idx_holdings_status ON holdings(status);

-- Holding values (point-in-time valuations for holdings)
CREATE TABLE IF NOT EXISTS holding_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    holding_id INTEGER NOT NULL,
    as_of_date DATE NOT NULL,
    as_of_datetime TEXT,                -- ISO-8601 timestamp for intraday precision
    quantity REAL NOT NULL,
    price REAL,                         -- price per unit
    market_value REAL,                  -- total market value (quantity * price)
    accrued_interest REAL,              -- for bonds
    fees REAL,                          -- management fees, etc.
    source_id INTEGER NOT NULL,
    document_id INTEGER,                -- link to documents for provenance
    valuation_currency TEXT NOT NULL DEFAULT 'USD',
    fx_rate_used REAL NOT NULL DEFAULT 1.0,  -- FX rate applied (1.0 for USD)
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT,
    FOREIGN KEY (holding_id) REFERENCES holdings(id) ON DELETE CASCADE,
    FOREIGN KEY (source_id) REFERENCES asset_sources(id) ON DELETE RESTRICT,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE SET NULL,
    CHECK (json_valid(metadata) OR metadata IS NULL),
    CHECK (LENGTH(valuation_currency) = 3),
    -- Note: quantity can be negative for short positions; validation at application level
    CHECK (price >= 0 OR price IS NULL),
    CHECK (market_value >= 0 OR market_value IS NULL),
    UNIQUE(holding_id, as_of_date, source_id)
);

CREATE INDEX IF NOT EXISTS idx_holding_values_holding_date
    ON holding_values(holding_id, as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_holding_values_date ON holding_values(as_of_date);
CREATE INDEX IF NOT EXISTS idx_holding_values_source ON holding_values(source_id);
CREATE INDEX IF NOT EXISTS idx_holding_values_document ON holding_values(document_id);

-- Asset prices (instrument-level price history, separate from holding values)
CREATE TABLE IF NOT EXISTS asset_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instrument_id INTEGER NOT NULL,
    as_of_date DATE NOT NULL,
    as_of_datetime TEXT,                -- ISO-8601 for intraday
    price REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    source_id INTEGER,
    metadata TEXT,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (instrument_id) REFERENCES instruments(id) ON DELETE CASCADE,
    FOREIGN KEY (source_id) REFERENCES asset_sources(id) ON DELETE SET NULL,
    CHECK (json_valid(metadata) OR metadata IS NULL),
    CHECK (LENGTH(currency) = 3),
    CHECK (price >= 0),
    UNIQUE(instrument_id, as_of_date, source_id)
);

CREATE INDEX IF NOT EXISTS idx_asset_prices_instrument_date
    ON asset_prices(instrument_id, as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_asset_prices_date ON asset_prices(as_of_date);

-- Instrument classifications (mapping instruments to asset classes)
-- An instrument can have multiple classifications if needed
CREATE TABLE IF NOT EXISTS instrument_classifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instrument_id INTEGER NOT NULL,
    asset_class_id INTEGER NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT TRUE,  -- primary classification
    metadata TEXT,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (instrument_id) REFERENCES instruments(id) ON DELETE CASCADE,
    FOREIGN KEY (asset_class_id) REFERENCES asset_classes(id) ON DELETE RESTRICT,
    CHECK (json_valid(metadata) OR metadata IS NULL),
    UNIQUE(instrument_id, asset_class_id)
);

CREATE INDEX IF NOT EXISTS idx_instrument_classifications_instrument
    ON instrument_classifications(instrument_id);
CREATE INDEX IF NOT EXISTS idx_instrument_classifications_class
    ON instrument_classifications(asset_class_id);

-- Portfolio targets (for rebalance suggestions)
CREATE TABLE IF NOT EXISTS portfolio_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,                -- 'account' or 'portfolio'
    scope_id INTEGER,                   -- account_id if scope='account', NULL for global portfolio
    asset_class_id INTEGER NOT NULL,
    target_weight REAL NOT NULL,        -- target allocation percentage (0-100)
    as_of_date DATE NOT NULL,           -- when this target was set
    metadata TEXT,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (asset_class_id) REFERENCES asset_classes(id) ON DELETE RESTRICT,
    CHECK (json_valid(metadata) OR metadata IS NULL),
    CHECK (scope IN ('account', 'portfolio')),
    CHECK (target_weight >= 0 AND target_weight <= 100)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_targets_scope
    ON portfolio_targets(scope, scope_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_targets_class
    ON portfolio_targets(asset_class_id);

COMMIT;
