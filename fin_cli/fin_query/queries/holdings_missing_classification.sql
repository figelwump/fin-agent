-- holdings_missing_classification.sql
-- Instruments without asset class assignments.

SELECT
    i.id AS instrument_id,
    i.name AS instrument_name,
    i.symbol,
    i.exchange,
    i.vehicle_type,
    i.currency,
    COUNT(DISTINCT h.id) AS holding_count,
    COUNT(DISTINCT h.account_id) AS account_count
FROM instruments i
LEFT JOIN instrument_classifications ic ON ic.instrument_id = i.id
LEFT JOIN holdings h ON h.instrument_id = i.id AND h.status = 'active'
WHERE ic.id IS NULL
GROUP BY i.id, i.name, i.symbol, i.exchange, i.vehicle_type, i.currency
ORDER BY COUNT(DISTINCT h.id) DESC, i.name
LIMIT :limit;
