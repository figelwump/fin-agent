SELECT
    category,
    subcategory,
    transaction_count,
    last_used,
    user_approved,
    auto_generated
FROM categories
WHERE (:category IS NULL OR category LIKE :category)
  AND (:subcategory IS NULL OR subcategory LIKE :subcategory)
ORDER BY category, subcategory
LIMIT :limit;
