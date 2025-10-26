SELECT
    c.category,
    c.subcategory,
    COUNT(t.id) as transaction_count,
    MAX(t.date) as last_used,
    c.user_approved,
    c.auto_generated
FROM categories c
LEFT JOIN transactions t ON t.category_id = c.id
WHERE (:category IS NULL OR c.category LIKE :category)
  AND (:subcategory IS NULL OR c.subcategory LIKE :subcategory)
GROUP BY c.id, c.category, c.subcategory, c.user_approved, c.auto_generated
ORDER BY c.category, c.subcategory
LIMIT :limit;
