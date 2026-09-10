"""
RetailMind :: the SQL behind every number on screen.

Queries live here as strings rather than being buried in page code, because the
app displays each one next to the chart it produced. If a number is on a
dashboard, the query that made it is one click away.

Two decisions worth knowing about before reading these:

1. "Today" is max(order_date), never CURRENT_DATE. The warehouse ends on
   2025-12-31; anchoring recency to the real clock would push every customer into
   the lapsed bucket and quietly break RFM.

2. Most of these read materialized views rather than the fact table. Aggregating
   9.4M orders on every page load took 6-9 seconds per chart, and no index fixes
   that -- these queries genuinely need every row, so the answer is to stop
   recomputing history that cannot change. sql/05_rollups.sql holds the
   definitions, and BEFORE_ROLLUP below keeps the original full-scan versions so
   the cost of the old path stays visible instead of being quietly deleted.
"""

# --------------------------------------------------------------------- exec overview
# Sums and counts roll up; DISTINCT counts do not. mv_monthly is grouped by
# (month, brand, channel), so adding its customer counts together counts anyone
# who bought in two months twice -- across the full window that inflated 100,403
# customers to 1,093,257. Revenue and order counts are additive and still come
# from the rollup; the distinct customer count has to touch the fact table, and
# costs about 1.4s for it. That is the honest price of the measure, and it is why
# it is cached rather than pre-aggregated.
KPIS = """
WITH agg AS (
    SELECT sum(orders) AS orders, sum(revenue) AS revenue
    FROM mv_monthly
    WHERE month BETWEEN date_trunc('month', %(start)s::date) AND %(end)s::date
      AND (%(brand)s::smallint IS NULL OR brand_id = %(brand)s::smallint)
),
people AS (
    SELECT count(DISTINCT customer_id) AS active_customers
    FROM orders
    WHERE order_date BETWEEN %(start)s::date AND %(end)s::date
      AND (%(brand)s::smallint IS NULL OR brand_id = %(brand)s::smallint)
)
SELECT
    agg.orders,
    agg.revenue,
    people.active_customers,
    agg.revenue / nullif(agg.orders, 0)                 AS aov,
    agg.revenue / nullif(people.active_customers, 0)    AS revenue_per_customer
FROM agg, people
"""

# Lifetime measure, deliberately not date-filtered: whether someone ever came
# back is a property of the customer, not of the window you happen to be viewing.
REPEAT_RATE = """
SELECT
    count(*)                                            AS customers,
    count(*) FILTER (WHERE frequency = 1)               AS single_visit,
    count(*) FILTER (WHERE frequency > 1)               AS repeat_customers,
    100.0 * count(*) FILTER (WHERE frequency > 1) / count(*) AS repeat_rate_pct
FROM mv_customer
WHERE (%(brand)s::smallint IS NULL OR brand_id = %(brand)s::smallint)
"""

MONTHLY_TREND = """
SELECT
    month,
    sum(orders)                             AS orders,
    sum(revenue)                            AS revenue,
    sum(revenue) / nullif(sum(orders), 0)   AS aov
FROM mv_monthly
WHERE month BETWEEN date_trunc('month', %(start)s::date) AND %(end)s::date
  AND (%(brand)s::smallint IS NULL OR brand_id = %(brand)s::smallint)
GROUP BY month
ORDER BY month
"""

# Same split as KPIS: additive measures from the rollup, the distinct customer
# count from the fact table, joined on brand.
REVENUE_BY_BRAND = """
WITH agg AS (
    SELECT brand_id, sum(orders) AS orders, sum(revenue) AS revenue
    FROM mv_monthly
    WHERE month BETWEEN date_trunc('month', %(start)s::date) AND %(end)s::date
    GROUP BY brand_id
),
people AS (
    SELECT brand_id, count(DISTINCT customer_id) AS customers
    FROM orders
    WHERE order_date BETWEEN %(start)s::date AND %(end)s::date
    GROUP BY brand_id
)
SELECT
    b.brand_name,
    b.category,
    agg.orders,
    agg.revenue,
    people.customers,
    agg.revenue / nullif(agg.orders, 0) AS aov
FROM agg
JOIN brands b  ON b.brand_id = agg.brand_id
LEFT JOIN people ON people.brand_id = agg.brand_id
ORDER BY agg.revenue DESC
"""

CHANNEL_MIX = """
SELECT
    channel,
    sum(orders)   AS orders,
    sum(revenue)  AS revenue
FROM mv_monthly
WHERE month BETWEEN date_trunc('month', %(start)s::date) AND %(end)s::date
  AND (%(brand)s::smallint IS NULL OR brand_id = %(brand)s::smallint)
GROUP BY channel
ORDER BY revenue DESC
"""


# --------------------------------------------------------------------- RFM
# Quintiles via ntile() rather than hand-picked thresholds, so the split still
# works when it is pointed at one brand instead of all five. Recency is scored on
# last_order ascending, so a higher r always means "bought more recently" and all
# three scores read in the same direction.
RFM = """
WITH as_of AS (
    SELECT max(last_order) AS today FROM mv_customer
),
base AS (
    SELECT
        c.customer_id,
        c.last_order,
        (SELECT today FROM as_of) - c.last_order AS recency_days,
        c.frequency,
        c.monetary
    FROM mv_customer c
    WHERE (%(brand)s::smallint IS NULL OR c.brand_id = %(brand)s::smallint)
),
scored AS (
    SELECT *,
        ntile(5) OVER (ORDER BY last_order ASC) AS r,
        ntile(5) OVER (ORDER BY frequency ASC)  AS f,
        ntile(5) OVER (ORDER BY monetary ASC)   AS m
    FROM base
),
labelled AS (
    SELECT *,
        CASE
            WHEN r >= 4 AND f >= 4 THEN 'Champions'
            WHEN r >= 3 AND f >= 3 THEN 'Loyal'
            WHEN r >= 4 AND f <= 2 THEN 'New / Promising'
            WHEN r <= 2 AND f >= 3 THEN 'At Risk'
            WHEN r <= 2 AND f <= 2 THEN 'Lost'
            ELSE 'Needs Attention'
        END AS segment
    FROM scored
)
SELECT
    segment,
    count(*)                 AS customers,
    round(avg(recency_days)) AS avg_recency_days,
    round(avg(frequency), 1) AS avg_orders,
    round(avg(monetary))     AS avg_spend,
    sum(monetary)            AS total_revenue
FROM labelled
GROUP BY segment
ORDER BY total_revenue DESC
"""


# --------------------------------------------------------------------- cohorts
COHORTS = """
SELECT
    cohort_month,
    month_n,
    sum(customers) AS customers
FROM mv_cohort
WHERE (%(brand)s::smallint IS NULL OR brand_id = %(brand)s::smallint)
GROUP BY cohort_month, month_n
ORDER BY cohort_month, month_n
"""


# --------------------------------------------------------------------- campaigns
# Response rate cannot answer "did this campaign work" -- customers who were going
# to buy anyway still open the message and still convert. Every campaign holds out
# a random ~15% of its audience, so treated-minus-control gives incremental
# revenue, which is the only figure worth putting next to the cost.
CAMPAIGN_PERFORMANCE = """
SELECT
    campaign_id, campaign_name, campaign_type, channel,
    cost, treated, holdout,
    open_rate, click_rate,
    treated_conv_pct, holdout_conv_pct,
    treated_rev_per_cust, holdout_rev_per_cust
FROM mv_campaign
WHERE (%(brand)s::smallint IS NULL OR brand_id = %(brand)s::smallint)
ORDER BY campaign_id
"""


# --------------------------------------------------------------------- meta
BRANDS = "SELECT brand_id, brand_name, category FROM brands ORDER BY brand_id"

DATE_RANGE = "SELECT min(order_date) AS lo, max(order_date) AS hi FROM orders"

WAREHOUSE_STATS = """
SELECT
    (SELECT sum(orders)::bigint FROM mv_monthly)                   AS orders,
    (SELECT count(*) FROM mv_customer)                             AS customers,
    (SELECT count(*) FROM campaign_sends)                          AS sends,
    (SELECT count(*) FROM campaigns)                               AS campaigns,
    (SELECT count(*) FROM stores)                                  AS stores,
    (SELECT pg_size_pretty(pg_total_relation_size('orders')))      AS orders_size,
    (SELECT pg_size_pretty(pg_database_size(current_database())))  AS db_size
"""


# --------------------------------------------------------------------- the old path
# Kept deliberately. These are the queries the dashboard ran before the rollups
# existed, with the times they took against 9.4M orders. The Query Lab renders
# them so the cost of the original approach stays visible rather than being
# quietly deleted along with the problem.
BEFORE_ROLLUP = {
    "Monthly trend": {
        "ms": 6255,
        "sql": """
SELECT date_trunc('month', order_date)::date AS month,
       count(*) AS orders, sum(amount) AS revenue,
       count(DISTINCT customer_id) AS customers
FROM orders
WHERE order_date BETWEEN %(start)s AND %(end)s
GROUP BY 1 ORDER BY 1
""",
    },
    "Revenue by brand": {
        "ms": 8598,
        "sql": """
SELECT b.brand_name, count(*) AS orders, sum(o.amount) AS revenue,
       count(DISTINCT o.customer_id) AS customers
FROM orders o JOIN brands b ON b.brand_id = o.brand_id
WHERE o.order_date BETWEEN %(start)s AND %(end)s
GROUP BY b.brand_name ORDER BY revenue DESC
""",
    },
    "Cohort retention": {
        "ms": 7625,
        "sql": """
WITH first_order AS (
    SELECT customer_id, min(order_date) AS first_dt FROM orders GROUP BY 1
), activity AS (
    SELECT date_trunc('month', f.first_dt)::date AS cohort_month, o.customer_id,
           ((date_part('year',o.order_date)-date_part('year',f.first_dt))*12
           +(date_part('month',o.order_date)-date_part('month',f.first_dt)))::int AS month_n
    FROM first_order f JOIN orders o ON o.customer_id = f.customer_id
)
SELECT cohort_month, month_n, count(DISTINCT customer_id) AS customers
FROM activity WHERE month_n BETWEEN 0 AND 11 GROUP BY 1,2
""",
    },
}
