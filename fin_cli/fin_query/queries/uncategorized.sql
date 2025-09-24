SELECT
    t.id,
    t.date,
    t.merchant,
    t.amount,
    t.original_description,
    a.name AS account_name
FROM transactions AS t
LEFT JOIN accounts AS a ON a.id = t.account_id
WHERE t.category_id IS NULL
ORDER BY t.date DESC;
