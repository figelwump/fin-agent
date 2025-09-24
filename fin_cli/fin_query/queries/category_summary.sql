SELECT
    c.category AS category,
    COALESCE(c.subcategory, '') AS subcategory,
    SUM(t.amount) AS total_amount,
    COUNT(*) AS transaction_count
FROM transactions AS t
JOIN categories AS c ON c.id = t.category_id
WHERE substr(t.date, 1, 7) = :month
  AND (:account_id IS NULL OR t.account_id = :account_id)
GROUP BY c.category, c.subcategory
ORDER BY total_amount DESC;
