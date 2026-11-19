-- name: data_quality
SELECT COUNT(*) AS raw_rows,
       COUNT(*) - COUNT(DISTINCT order_id) AS duplicate_rows,
       SUM(CASE WHEN delivery_minutes < 0 THEN 1 ELSE 0 END) AS invalid_delivery_time
FROM orders_raw;

-- name: clean_orders
CREATE OR REPLACE TABLE orders AS
WITH dedup AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY order_ts) AS rn
  FROM orders_raw
)
SELECT order_id, customer_id, store_id, order_ts, distance_km, status, defect_type,
       CASE WHEN delivery_minutes < 0 THEN NULL ELSE delivery_minutes END AS delivery_minutes,
       HOUR(order_ts) BETWEEN 18 AND 21 AS is_peak
FROM dedup WHERE rn = 1;

-- name: overall_kpis
SELECT COUNT(*) AS orders,
       ROUND(AVG(delivery_minutes), 1) AS avg_mins,
       ROUND(QUANTILE_CONT(delivery_minutes, 0.9), 1) AS p90_mins,
       ROUND(100 * AVG(CASE WHEN delivery_minutes <= 15 THEN 1.0 ELSE 0 END) FILTER (WHERE status = 'delivered'), 1) AS on_time_pct,
       ROUND(100 * AVG(CASE WHEN defect_type IS NOT NULL THEN 1.0 ELSE 0 END) FILTER (WHERE status = 'delivered'), 2) AS defect_pct,
       ROUND(100 * AVG(CASE WHEN status = 'cancelled' THEN 1.0 ELSE 0 END), 2) AS cancel_pct
FROM orders;

-- name: weekly_kpis_anomalies
WITH weekly AS (
  SELECT DATE_TRUNC('week', order_ts) AS week,
         COUNT(*) AS orders,
         AVG(CASE WHEN delivery_minutes > 15 THEN 1.0 ELSE 0 END) FILTER (WHERE status = 'delivered') AS late_rate
  FROM orders GROUP BY 1
), stats AS (
  SELECT *,
         AVG(late_rate)    OVER w AS rolling_avg,
         STDDEV(late_rate) OVER w AS rolling_sd,
         late_rate - LAG(late_rate) OVER (ORDER BY week) AS wow_change
  FROM weekly
  WINDOW w AS (ORDER BY week ROWS BETWEEN 8 PRECEDING AND 1 PRECEDING)
)
SELECT week::DATE AS week, orders, ROUND(100 * late_rate, 1) AS late_pct,
       ROUND(100 * rolling_avg, 1) AS rolling_8w_pct,
       late_rate > rolling_avg + 2 * rolling_sd AS is_anomaly
FROM stats ORDER BY week;

-- name: store_peak_ranking
WITH s AS (
  SELECT o.store_id, st.zone,
         ROUND(100 * AVG(CASE WHEN delivery_minutes > 15 THEN 1.0 ELSE 0 END) FILTER (WHERE is_peak), 1) AS peak_late_pct,
         ROUND(100 * AVG(CASE WHEN delivery_minutes > 15 THEN 1.0 ELSE 0 END) FILTER (WHERE NOT is_peak), 1) AS offpeak_late_pct,
         ROUND(QUANTILE_CONT(delivery_minutes, 0.9) FILTER (WHERE is_peak), 1) AS peak_p90_mins
  FROM orders o JOIN stores st USING (store_id)
  WHERE status = 'delivered' GROUP BY 1, 2
)
SELECT RANK() OVER (ORDER BY peak_late_pct DESC) AS rnk, * FROM s ORDER BY rnk;

-- name: late_share_from_top3_peak
WITH late AS (
  SELECT store_id, is_peak FROM orders WHERE delivery_minutes > 15
), top3 AS (
  SELECT store_id FROM orders WHERE status = 'delivered' AND is_peak
  GROUP BY 1 ORDER BY AVG(CASE WHEN delivery_minutes > 15 THEN 1.0 ELSE 0 END) DESC LIMIT 3
)
SELECT ROUND(100 * AVG(CASE WHEN is_peak AND store_id IN (SELECT store_id FROM top3) THEN 1.0 ELSE 0 END), 1) AS pct_of_late_orders,
       ROUND(100.0 * (SELECT COUNT(*) FROM orders WHERE is_peak AND store_id IN (SELECT store_id FROM top3)) / (SELECT COUNT(*) FROM orders), 1) AS pct_of_all_orders
FROM late;

-- name: defects_by_delivery_time
SELECT CASE WHEN delivery_minutes <= 10 THEN '0-10' WHEN delivery_minutes <= 15 THEN '10-15'
            WHEN delivery_minutes <= 20 THEN '15-20' ELSE '20+' END AS mins_bucket,
       COUNT(*) AS orders,
       ROUND(100 * AVG(CASE WHEN defect_type IS NOT NULL THEN 1.0 ELSE 0 END), 2) AS defect_pct
FROM orders WHERE status = 'delivered' AND delivery_minutes IS NOT NULL
GROUP BY 1 ORDER BY 1;

-- name: inventory_turns
WITH cogs AS (
  SELECT p.category, SUM(i.qty * p.unit_cost) AS cogs
  FROM order_items i
  JOIN orders o USING (order_id)
  JOIN products p USING (product_id)
  WHERE o.status = 'delivered' GROUP BY 1
), inv AS (
  SELECT category, AVG(total) AS avg_inventory
  FROM (SELECT date, category, SUM(inventory_value) AS total FROM inventory_daily GROUP BY 1, 2)
  GROUP BY 1
), so AS (
  SELECT category, ROUND(AVG(stockout_skus), 2) AS avg_daily_stockout_skus_per_store FROM inventory_daily GROUP BY 1
)
SELECT category, ROUND(cogs / avg_inventory * 365 / 184, 1) AS annual_inventory_turns,
       avg_daily_stockout_skus_per_store
FROM cogs JOIN inv USING (category) JOIN so USING (category)
ORDER BY annual_inventory_turns DESC;

-- name: promo_pilot_did
WITH daily AS (
  SELECT o.store_id, o.order_ts::DATE AS d,
         SUM(i.qty * i.unit_price) FILTER (WHERE p.category = 'Dairy & Breakfast') AS dairy_rev,
         COUNT(DISTINCT o.order_id) AS orders
  FROM orders o JOIN order_items i USING (order_id) JOIN products p USING (product_id)
  WHERE o.status = 'delivered' AND o.order_ts::DATE BETWEEN '2025-08-18' AND '2025-09-14'
  GROUP BY 1, 2
), labeled AS (
  SELECT *, store_id IN ('DS02','DS05','DS09','DS14','DS18','DS23') AS pilot,
            d >= DATE '2025-09-01' AS during
  FROM daily
), agg AS (
  SELECT pilot, during, AVG(dairy_rev) AS dairy_rev_per_store_day FROM labeled GROUP BY 1, 2
)
SELECT ROUND(MAX(CASE WHEN pilot AND during THEN dairy_rev_per_store_day END), 0) AS pilot_during,
       ROUND(MAX(CASE WHEN pilot AND NOT during THEN dairy_rev_per_store_day END), 0) AS pilot_before,
       ROUND(MAX(CASE WHEN NOT pilot AND during THEN dairy_rev_per_store_day END), 0) AS control_during,
       ROUND(MAX(CASE WHEN NOT pilot AND NOT during THEN dairy_rev_per_store_day END), 0) AS control_before,
       ROUND(100 * ((MAX(CASE WHEN pilot AND during THEN dairy_rev_per_store_day END) / MAX(CASE WHEN pilot AND NOT during THEN dairy_rev_per_store_day END))
                  - (MAX(CASE WHEN NOT pilot AND during THEN dairy_rev_per_store_day END) / MAX(CASE WHEN NOT pilot AND NOT during THEN dairy_rev_per_store_day END))), 1) AS did_lift_pct_pts
FROM agg;
