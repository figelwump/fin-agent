SELECT
    t.date,
    t.merchant,
    t.original_description,
    t.amount,
    c.category,
    c.subcategory,
    a.name AS account_name,
    a.institution AS institution
FROM transactions AS t
LEFT JOIN categories AS c ON c.id = t.category_id
LEFT JOIN accounts AS a ON a.id = t.account_id
WHERE (:category IS NULL OR c.category LIKE :category)
  AND (:subcategory IS NULL OR c.subcategory LIKE :subcategory)
ORDER BY t.date DESC, t.id DESC
LIMIT :limit;
