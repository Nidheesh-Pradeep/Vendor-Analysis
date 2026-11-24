SELECT
    vendor,
    COUNT(DISTINCT po_so) AS purchase_orders,
    COUNT(*) AS line_rows,
    ROUND(SUM(line_item_value_numeric), 2) AS line_item_value
FROM stg_shipments
GROUP BY vendor
ORDER BY line_item_value DESC;


