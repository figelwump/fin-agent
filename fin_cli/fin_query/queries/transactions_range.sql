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
WHERE
    (:start_date IS NULL OR t.date >= :start_date)
    AND (:end_date IS NULL OR t.date < :end_date)
ORDER BY t.date DESC, t.id DESC
LIMIT :limit;
