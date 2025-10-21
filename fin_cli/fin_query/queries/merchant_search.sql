SELECT
    t.date,
    t.merchant,
    t.original_description,
    t.amount,
    c.category,
    c.subcategory,
    a.name AS account_name,
    a.institution AS institution
FROM transactions t
LEFT JOIN categories c ON c.id = t.category_id
LEFT JOIN accounts a ON a.id = t.account_id
WHERE t.merchant LIKE :pattern
ORDER BY t.date ASC, t.id ASC
LIMIT :limit;
