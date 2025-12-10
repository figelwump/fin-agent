-- stale_holdings.sql
-- Holdings without recent valuation updates.

WITH latest_value_dates AS (
    SELECT
        holding_id,
        MAX(as_of_date) AS last_value_date
    FROM holding_values
    GROUP BY holding_id
)
SELECT
    h.id AS holding_id,
    a.name AS account_name,
    a.institution,
    i.name AS instrument_name,
    i.symbol,
    i.vehicle_type,
    h.status,
    lvd.last_value_date,
    CAST(julianday('now') - julianday(lvd.last_value_date) AS INTEGER) AS days_since_update
FROM holdings h
JOIN accounts a ON a.id = h.account_id
JOIN instruments i ON i.id = h.instrument_id
LEFT JOIN latest_value_dates lvd ON lvd.holding_id = h.id
WHERE h.status = 'active'
  AND (
      lvd.last_value_date IS NULL
      OR julianday('now') - julianday(lvd.last_value_date) > :days
  )
ORDER BY
    CASE WHEN lvd.last_value_date IS NULL THEN 1 ELSE 0 END DESC,
    days_since_update DESC
LIMIT :limit;
