-- holding_latest_values.sql
-- Latest valuation for each holding using source priority then recency.
-- Source precedence: statement (priority 1) > manual (2) > api (3)

WITH ranked_values AS (
    SELECT
        hv.*,
        asrc.priority AS source_priority,
        ROW_NUMBER() OVER (
            PARTITION BY hv.holding_id
            ORDER BY asrc.priority ASC, hv.as_of_date DESC, hv.ingested_at DESC
        ) AS rn
    FROM holding_values hv
    JOIN asset_sources asrc ON asrc.id = hv.source_id
)
SELECT
    h.id AS holding_id,
    a.name AS account_name,
    a.institution,
    i.name AS instrument_name,
    i.symbol,
    i.vehicle_type,
    h.status,
    h.position_side,
    rv.as_of_date,
    rv.quantity,
    rv.price,
    rv.market_value,
    rv.valuation_currency,
    asrc.name AS source_name,
    h.cost_basis_total,
    h.cost_basis_per_unit
FROM holdings h
JOIN accounts a ON a.id = h.account_id
JOIN instruments i ON i.id = h.instrument_id
LEFT JOIN ranked_values rv ON rv.holding_id = h.id AND rv.rn = 1
LEFT JOIN asset_sources asrc ON asrc.id = rv.source_id
WHERE (:account_id IS NULL OR h.account_id = :account_id)
  AND (:status IS NULL OR h.status = :status)
ORDER BY a.institution, a.name, i.symbol, i.name
LIMIT :limit;
