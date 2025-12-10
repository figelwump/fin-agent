-- allocation_by_class.sql
-- Allocation breakdown by main and sub asset class.

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
      AND (:account_id IS NULL OR h.account_id = :account_id)
)
SELECT
    COALESCE(ac.main_class, 'unclassified') AS main_class,
    COALESCE(ac.sub_class, 'unknown') AS sub_class,
    COUNT(DISTINCT h.id) AS holding_count,
    COUNT(DISTINCT i.id) AS instrument_count,
    SUM(lv.market_value) AS total_value,
    ROUND(SUM(lv.market_value) * 100.0 / NULLIF(pt.total_value, 0), 2) AS allocation_pct
FROM holdings h
JOIN instruments i ON i.id = h.instrument_id
JOIN latest_values lv ON lv.holding_id = h.id AND lv.rn = 1
LEFT JOIN instrument_classifications ic ON ic.instrument_id = i.id AND ic.is_primary = 1
LEFT JOIN asset_classes ac ON ac.id = ic.asset_class_id
CROSS JOIN portfolio_total pt
WHERE h.status = 'active'
  AND (:account_id IS NULL OR h.account_id = :account_id)
GROUP BY ac.main_class, ac.sub_class
ORDER BY SUM(lv.market_value) DESC;
