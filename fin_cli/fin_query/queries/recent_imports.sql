SELECT
    t.id,
    t.import_date,
    t.date,
    t.merchant,
    t.amount,
    c.category AS category,
    c.subcategory
FROM transactions AS t
LEFT JOIN categories AS c ON c.id = t.category_id
ORDER BY
    CASE WHEN t.import_date IS NULL THEN 1 ELSE 0 END,
    t.import_date DESC,
    t.id DESC
LIMIT :limit;
