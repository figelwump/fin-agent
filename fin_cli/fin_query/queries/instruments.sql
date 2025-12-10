-- instruments.sql
-- Instrument catalog with classifications.

SELECT
    i.id,
    i.name,
    i.symbol,
    i.exchange,
    i.currency,
    i.vehicle_type,
    i.identifiers,
    ac.main_class,
    ac.sub_class,
    COUNT(DISTINCT h.id) AS holding_count
FROM instruments i
LEFT JOIN instrument_classifications ic ON ic.instrument_id = i.id AND ic.is_primary = 1
LEFT JOIN asset_classes ac ON ac.id = ic.asset_class_id
LEFT JOIN holdings h ON h.instrument_id = i.id AND h.status = 'active'
WHERE (:symbol IS NULL OR i.symbol LIKE :symbol)
  AND (:vehicle_type IS NULL OR i.vehicle_type = :vehicle_type)
GROUP BY i.id, i.name, i.symbol, i.exchange, i.currency, i.vehicle_type, i.identifiers, ac.main_class, ac.sub_class
ORDER BY i.symbol, i.name
LIMIT :limit;
