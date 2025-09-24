SELECT
    mp.pattern,
    COALESCE(c.category, '') AS category,
    COALESCE(c.subcategory, '') AS subcategory,
    mp.confidence,
    mp.usage_count,
    mp.learned_date
FROM merchant_patterns AS mp
LEFT JOIN categories AS c ON c.id = mp.category_id
WHERE (:pattern IS NULL OR mp.pattern LIKE :pattern)
ORDER BY mp.usage_count DESC, mp.pattern
LIMIT :limit;
