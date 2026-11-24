WITH vendor_spend AS (
    SELECT
        vendor,
        SUM(line_item_value_numeric) AS spend
    FROM stg_shipments
    GROUP BY vendor
),
ranked_spend AS (
    SELECT
        vendor,
        spend,
        SUM(spend) OVER (
            ORDER BY spend DESC
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_spend,
        SUM(spend) OVER () AS total_spend
    FROM vendor_spend
)
SELECT
    vendor,
    ROUND(spend, 2) AS spend,
    ROUND(100.0 * spend / NULLIF(total_spend, 0), 2) AS vendor_spend_pct,
    ROUND(100.0 * cumulative_spend / NULLIF(total_spend, 0), 2)
        AS cumulative_spend_pct
FROM ranked_spend
ORDER BY spend DESC;