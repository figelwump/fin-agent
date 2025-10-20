SELECT
    merchant,
    COUNT(*) AS count
FROM transactions
WHERE merchant IS NOT NULL
  AND merchant != ''
GROUP BY merchant
HAVING count >= COALESCE(:min_count, 1)
ORDER BY count DESC, merchant;
