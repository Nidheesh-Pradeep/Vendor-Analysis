WITH shipment_dates AS (
    SELECT
        vendor,
        asn_dn,
        MIN(date(scheduled_delivery_date_parsed)) AS scheduled_date,
        MAX(date(scheduled_delivery_date_parsed)) AS scheduled_date_max,
        MIN(date(delivered_to_client_date_parsed)) AS delivered_date,
        MAX(date(delivered_to_client_date_parsed)) AS delivered_date_max
    FROM stg_shipments
    GROUP BY vendor, asn_dn
),
shipment_checks AS (
    SELECT
        *,
        CASE
            WHEN scheduled_date = scheduled_date_max
             AND delivered_date = delivered_date_max
            THEN 1 ELSE 0
        END AS dates_consistent
    FROM shipment_dates
)
SELECT
    vendor,
    COUNT(*) AS shipments,
    SUM(dates_consistent) AS shipments_with_consistent_dates,
    SUM(
        CASE WHEN dates_consistent = 1
                   AND delivered_date <= scheduled_date
             THEN 1 ELSE 0 END
    ) AS early_or_on_time_shipments,
    SUM(
        CASE WHEN dates_consistent = 1
                   AND delivered_date > scheduled_date
             THEN 1 ELSE 0 END
    ) AS late_shipments,
    ROUND(
        100.0 * SUM(
            CASE WHEN dates_consistent = 1
                       AND delivered_date <= scheduled_date
                 THEN 1 ELSE 0 END
        ) / NULLIF(SUM(dates_consistent), 0),
        2
    ) AS early_or_on_time_pct
FROM shipment_checks
GROUP BY vendor
ORDER BY early_or_on_time_pct;