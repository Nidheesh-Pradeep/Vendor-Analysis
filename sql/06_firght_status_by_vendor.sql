WITH first_line AS (
    SELECT
        vendor,
        asn_dn,
        freight_status,
        freight_usd_numeric
    FROM stg_shipments
    WHERE LOWER(TRIM(first_line_designation)) = 'yes'
)
SELECT
    vendor,
    freight_status,
    COUNT(DISTINCT asn_dn) AS shipments,
    ROUND(SUM(freight_usd_numeric), 2) AS numeric_freight_usd
FROM first_line
GROUP BY vendor, freight_status
ORDER BY vendor, shipments DESC;