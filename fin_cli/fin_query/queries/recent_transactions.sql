SELECT
    t.id,
    t.date,
    t.merchant,
    t.amount,
    c.category AS category,
    c.subcategory,
    t.categorization_method,
    t.categorization_confidence
FROM transactions AS t
LEFT JOIN categories AS c ON c.id = t.category_id
WHERE (:month IS NULL OR substr(t.date, 1, 7) = :month)
ORDER BY t.date DESC, t.id DESC
LIMIT :limit;
