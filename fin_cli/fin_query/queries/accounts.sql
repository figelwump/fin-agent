-- Account catalog with transaction + holdings rollups.
WITH tx_stats AS (
    SELECT
        account_id,
        COUNT(*) AS transaction_count,
        MAX(date) AS last_transaction_date,
        SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) AS total_spend,
        SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS total_income
    FROM transactions
    GROUP BY account_id
),
holding_stats AS (
    SELECT
        h.account_id,
        COUNT(DISTINCT h.id) AS holdings_count,
        MAX(hv.as_of_date) AS last_valuation_date
    FROM holdings AS h
    LEFT JOIN holding_values AS hv ON hv.holding_id = h.id
    GROUP BY h.account_id
)
SELECT
    a.id,
    a.name,
    a.institution,
    a.account_type,
    a.last_4_digits,
    a.auto_detected,
    a.created_date,
    a.last_import,
    COALESCE(tx.transaction_count, 0) AS transaction_count,
    tx.last_transaction_date,
    COALESCE(tx.total_spend, 0) AS total_spend,
    COALESCE(tx.total_income, 0) AS total_income,
    COALESCE(hs.holdings_count, 0) AS holdings_count,
    hs.last_valuation_date
FROM accounts AS a
LEFT JOIN tx_stats AS tx ON tx.account_id = a.id
LEFT JOIN holding_stats AS hs ON hs.account_id = a.id
WHERE (:institution IS NULL OR a.institution = :institution)
  AND (:account_type IS NULL OR a.account_type = :account_type)
ORDER BY COALESCE(a.last_import, a.created_date) DESC, a.id DESC
LIMIT :limit;
