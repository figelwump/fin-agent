-- asset_classes.sql
-- Asset class taxonomy catalog.

SELECT
    ac.id,
    ac.main_class,
    ac.sub_class,
    ac.vehicle_type_default,
    COUNT(DISTINCT ic.instrument_id) AS instrument_count
FROM asset_classes ac
LEFT JOIN instrument_classifications ic ON ic.asset_class_id = ac.id
WHERE :main_class IS NULL OR ac.main_class = :main_class
GROUP BY ac.id, ac.main_class, ac.sub_class, ac.vehicle_type_default
ORDER BY ac.main_class, ac.sub_class
LIMIT :limit;
