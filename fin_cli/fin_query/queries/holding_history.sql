-- holding_history.sql
-- Value history for a specific holding over time.

SELECT
    hv.id,
    hv.as_of_date,
    hv.as_of_datetime,
    hv.quantity,
    hv.price,
    hv.market_value,
    hv.accrued_interest,
    hv.fees,
    hv.valuation_currency,
    hv.fx_rate_used,
    asrc.name AS source_name,
    d.document_hash,
    hv.ingested_at
FROM holding_values hv
JOIN asset_sources asrc ON asrc.id = hv.source_id
LEFT JOIN documents d ON d.id = hv.document_id
WHERE hv.holding_id = :holding_id
ORDER BY hv.as_of_date DESC, hv.ingested_at DESC
LIMIT :limit;
