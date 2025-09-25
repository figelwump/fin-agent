WITH params AS (
    SELECT
        date(:month || '-01') AS start_date,
        date(:month || '-01', '+1 month') AS end_date
)
SELECT
    t.id AS transaction_id,
    t.date AS date,
    t.merchant AS merchant,
    t.amount AS amount,
    t.account_id AS account_id,
    a.name AS account_name,
    a.institution AS institution,
    a.account_type AS account_type,
    t.category_id AS category_id,
    c.category AS category,
    c.subcategory AS subcategory,
    t.original_description AS original_description,
    t.categorization_method AS categorization_method,
    t.categorization_confidence AS categorization_confidence,
    t.metadata AS transaction_metadata,
    c.auto_generated AS category_auto_generated,
    c.user_approved AS category_user_approved
FROM transactions t
LEFT JOIN accounts a ON t.account_id = a.id
LEFT JOIN categories c ON t.category_id = c.id
JOIN params p
WHERE t.date >= p.start_date
  AND t.date < p.end_date
  AND (:account_id IS NULL OR t.account_id = :account_id)
  AND (:category IS NULL OR COALESCE(c.category, '') LIKE :category)
  AND (:subcategory IS NULL OR COALESCE(c.subcategory, '') LIKE :subcategory)
ORDER BY t.date ASC, t.id ASC;
