-- 007_asset_classes_seed.sql
-- Seed initial asset classes taxonomy and default asset sources.
-- Uses INSERT OR IGNORE for idempotent re-runs.

BEGIN;

-- Seed asset classes
-- Main classes: equities, bonds, alternatives, cash, other
-- Sub-classes represent more granular categories
-- Note: ETFs are vehicles (vehicle_type), not asset classes

-- Equities
INSERT OR IGNORE INTO asset_classes (main_class, sub_class, vehicle_type_default) VALUES
    ('equities', 'US equity', 'stock'),
    ('equities', 'intl equity', 'stock'),
    ('equities', 'emerging markets', 'stock'),
    ('equities', 'small cap', 'stock'),
    ('equities', 'large cap', 'stock'),
    ('equities', 'sector fund', 'ETF');

-- Bonds / Fixed Income
INSERT OR IGNORE INTO asset_classes (main_class, sub_class, vehicle_type_default) VALUES
    ('bonds', 'treasury', 'bond'),
    ('bonds', 'muni', 'bond'),
    ('bonds', 'corporate IG', 'bond'),
    ('bonds', 'corporate HY', 'bond'),
    ('bonds', 'intl bond', 'bond'),
    ('bonds', 'TIPS', 'bond'),
    ('bonds', 'agency', 'bond');

-- Alternatives
INSERT OR IGNORE INTO asset_classes (main_class, sub_class, vehicle_type_default) VALUES
    ('alternatives', 'private equity', 'fund_LP'),
    ('alternatives', 'VC/Angel', 'fund_LP'),
    ('alternatives', 'real estate fund', 'fund_LP'),
    ('alternatives', 'hedge fund', 'fund_LP'),
    ('alternatives', 'commodities', 'ETF'),
    ('alternatives', 'crypto', 'crypto'),
    ('alternatives', 'REIT', 'stock');

-- Cash / Cash Equivalents
INSERT OR IGNORE INTO asset_classes (main_class, sub_class, vehicle_type_default) VALUES
    ('cash', 'cash sweep', 'MMF'),
    ('cash', 'money market', 'MMF'),
    ('cash', 'savings', NULL),
    ('cash', 'CD', NULL),
    ('cash', 'treasury bill', 'bond');

-- Other / Unknown (catch-all to avoid import failures)
INSERT OR IGNORE INTO asset_classes (main_class, sub_class, vehicle_type_default) VALUES
    ('other', 'unknown', NULL),
    ('other', 'pending classification', NULL),
    ('other', 'structured product', 'note'),
    ('other', 'insurance product', NULL),
    ('other', 'options', 'option');

-- Seed default asset sources with priority levels
-- Priority: statement=1 (highest), manual=2, api=3 (lowest)
INSERT OR IGNORE INTO asset_sources (name, source_type, priority) VALUES
    ('Statement Import', 'statement', 1),
    ('Manual Entry', 'manual', 2),
    ('API Sync', 'api', 3);

-- Common broker sources (statement type)
INSERT OR IGNORE INTO asset_sources (name, source_type, priority, contact_url) VALUES
    ('UBS Statement', 'statement', 1, 'https://www.ubs.com'),
    ('Schwab Statement', 'statement', 1, 'https://www.schwab.com'),
    ('Mercury Statement', 'statement', 1, 'https://mercury.com'),
    ('AngelList Statement', 'statement', 1, 'https://angellist.com'),
    ('Fidelity Statement', 'statement', 1, 'https://www.fidelity.com'),
    ('Vanguard Statement', 'statement', 1, 'https://www.vanguard.com');

COMMIT;
