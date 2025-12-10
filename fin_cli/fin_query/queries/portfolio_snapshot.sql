-- portfolio_snapshot.sql
-- Current portfolio snapshot with holdings, values, and classifications.
-- Joins accounts, holdings, latest values, instruments, and asset classes.

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
)
SELECT
    h.id AS holding_id,
    a.id AS account_id,
    a.name AS account_name,
    a.institution,
    i.id AS instrument_id,
    i.name AS instrument_name,
    i.symbol,
    i.exchange,
    i.currency AS instrument_currency,
    i.vehicle_type,
    h.status,
    h.position_side,
    lv.as_of_date,
    lv.quantity,
    lv.price,
    lv.market_value,
    lv.valuation_currency,
    lv.fx_rate_used,
    ac.main_class,
    ac.sub_class,
    h.cost_basis_total,
    h.cost_basis_per_unit,
    h.cost_basis_method,
    asrc.name AS source_name
FROM holdings h
JOIN accounts a ON a.id = h.account_id
JOIN instruments i ON i.id = h.instrument_id
LEFT JOIN latest_values lv ON lv.holding_id = h.id AND lv.rn = 1
LEFT JOIN asset_sources asrc ON asrc.id = lv.source_id
LEFT JOIN instrument_classifications ic ON ic.instrument_id = i.id AND ic.is_primary = 1
LEFT JOIN asset_classes ac ON ac.id = ic.asset_class_id
WHERE h.status = 'active'
  AND (:account_id IS NULL OR h.account_id = :account_id)
ORDER BY a.institution, a.name, COALESCE(lv.market_value, 0) DESC
LIMIT :limit;
