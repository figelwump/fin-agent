-- allocation_by_account.sql
-- Allocation breakdown by account.

WITH latest_values AS (
    SELECT
        hv.*,
        asrc.priority AS source_priority,
        ROW_NUMBER() OVER (
            PARTITION BY hv.holding_id
            ORDER BY
                CASE WHEN :as_of_date IS NOT NULL AND hv.as_of_date <= :as_of_date THEN 0 ELSE 1 END,
                asrc.priority ASC,
                hv.as_of_date DESC,
                hv.ingested_at DESC
        ) AS rn
    FROM holding_values hv
    JOIN asset_sources asrc ON asrc.id = hv.source_id
    WHERE :as_of_date IS NULL OR hv.as_of_date <= :as_of_date
),
portfolio_total AS (
    SELECT SUM(lv.market_value) AS total_value
    FROM holdings h
    JOIN latest_values lv ON lv.holding_id = h.id AND lv.rn = 1
    WHERE h.status = 'active'
)
SELECT
    a.id AS account_id,
    a.name AS account_name,
    a.institution,
    a.account_type,
    COUNT(DISTINCT h.id) AS holding_count,
    SUM(lv.market_value) AS total_value,
    ROUND(SUM(lv.market_value) * 100.0 / NULLIF(pt.total_value, 0), 2) AS allocation_pct
FROM holdings h
JOIN accounts a ON a.id = h.account_id
JOIN latest_values lv ON lv.holding_id = h.id AND lv.rn = 1
CROSS JOIN portfolio_total pt
WHERE h.status = 'active'
GROUP BY a.id, a.name, a.institution, a.account_type
ORDER BY SUM(lv.market_value) DESC;
