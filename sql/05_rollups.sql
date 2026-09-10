-- RetailMind :: dashboard rollups
--
-- Why these exist. Once the warehouse hit ~9M orders, the dashboard queries
-- themselves became the performance problem: the monthly trend took 6.2s, the
-- brand split 8.6s, and the cohort grid 7.6s. Every one of those is a full
-- aggregate over the whole fact table, and no index fixes that -- an index helps
-- you find rows, and these queries genuinely need all of them.
--
-- The fix is the one a warehouse actually uses: stop recomputing history on every
-- page load. History does not change. These materialized views collapse ~9M
-- order rows into a few thousand aggregate rows, refreshed on a schedule rather
-- than on every click.
--
-- The trade-off, stated plainly: the dashboard is now eventually consistent. For
-- three years of trading history that is free -- yesterday's revenue is not going
-- to change. For a real-time operational view it would be the wrong call.
--
-- One property of this dataset makes the rollups exact rather than approximate:
-- a customer belongs to exactly one brand, so summing distinct-customer counts
-- across brands cannot double-count. On a dataset where customers shop across
-- brands, count(DISTINCT ...) would not roll up like this and these views would
-- need a different shape (or HyperLogLog sketches).

-- --------------------------------------------------------------------- per customer
-- Powers RFM, repeat rate and CLV. 300k rows instead of ~9M.
DROP MATERIALIZED VIEW IF EXISTS mv_customer CASCADE;
CREATE MATERIALIZED VIEW mv_customer AS
SELECT
    o.customer_id,
    o.brand_id,
    min(o.order_date)   AS first_order,
    max(o.order_date)   AS last_order,
    count(*)            AS frequency,
    sum(o.amount)       AS monetary
FROM orders o
GROUP BY o.customer_id, o.brand_id;

CREATE UNIQUE INDEX ON mv_customer (customer_id);
CREATE INDEX ON mv_customer (brand_id);

-- --------------------------------------------------------------------- monthly
DROP MATERIALIZED VIEW IF EXISTS mv_monthly CASCADE;
CREATE MATERIALIZED VIEW mv_monthly AS
SELECT
    date_trunc('month', o.order_date)::date AS month,
    o.brand_id,
    o.channel,
    count(*)                        AS orders,
    sum(o.amount)                   AS revenue,
    count(DISTINCT o.customer_id)   AS customers
FROM orders o
GROUP BY 1, 2, 3;

CREATE INDEX ON mv_monthly (month);
CREATE INDEX ON mv_monthly (brand_id, month);

-- --------------------------------------------------------------------- cohorts
DROP MATERIALIZED VIEW IF EXISTS mv_cohort CASCADE;
CREATE MATERIALIZED VIEW mv_cohort AS
WITH first_order AS (
    SELECT customer_id, brand_id, min(order_date) AS first_dt
    FROM orders
    GROUP BY customer_id, brand_id
),
activity AS (
    SELECT
        f.brand_id,
        date_trunc('month', f.first_dt)::date AS cohort_month,
        o.customer_id,
        ( (date_part('year',  o.order_date) - date_part('year',  f.first_dt)) * 12
        + (date_part('month', o.order_date) - date_part('month', f.first_dt))
        )::int AS month_n
    FROM first_order f
    JOIN orders o ON o.customer_id = f.customer_id
)
SELECT brand_id, cohort_month, month_n, count(DISTINCT customer_id) AS customers
FROM activity
WHERE month_n BETWEEN 0 AND 11
GROUP BY brand_id, cohort_month, month_n;

CREATE INDEX ON mv_cohort (brand_id, cohort_month, month_n);

-- --------------------------------------------------------------------- campaigns
-- This one is not only about speed. The underlying join fans every send out
-- against the fact table and needs more shared memory than a default container
-- allocates; materialising it once keeps the page load cheap and predictable.
DROP MATERIALIZED VIEW IF EXISTS mv_campaign CASCADE;
CREATE MATERIALIZED VIEW mv_campaign AS
WITH sends AS (
    SELECT
        s.campaign_id, s.customer_id, s.is_holdout, s.opened, s.clicked,
        c.campaign_name, c.campaign_type, c.channel, c.cost, c.brand_id,
        c.start_date, c.end_date
    FROM campaign_sends s
    JOIN campaigns c ON c.campaign_id = s.campaign_id
),
attributed AS (
    SELECT
        sd.campaign_id, sd.campaign_name, sd.campaign_type, sd.channel,
        sd.cost, sd.brand_id, sd.customer_id, sd.is_holdout, sd.opened, sd.clicked,
        count(o.order_id)          AS n_orders,
        COALESCE(sum(o.amount), 0) AS revenue
    FROM sends sd
    LEFT JOIN orders o
           ON o.customer_id = sd.customer_id
          AND o.order_date BETWEEN sd.start_date AND sd.end_date
    GROUP BY sd.campaign_id, sd.campaign_name, sd.campaign_type, sd.channel,
             sd.cost, sd.brand_id, sd.customer_id, sd.is_holdout, sd.opened, sd.clicked
)
SELECT
    campaign_id, campaign_name, campaign_type, channel, brand_id,
    max(cost)                                                      AS cost,
    count(*) FILTER (WHERE NOT is_holdout)                         AS treated,
    count(*) FILTER (WHERE is_holdout)                             AS holdout,
    100.0 * avg((opened)::int)                                     AS open_rate,
    100.0 * avg((clicked)::int)                                    AS click_rate,
    100.0 * avg((n_orders > 0)::int) FILTER (WHERE NOT is_holdout) AS treated_conv_pct,
    100.0 * avg((n_orders > 0)::int) FILTER (WHERE is_holdout)     AS holdout_conv_pct,
    avg(revenue) FILTER (WHERE NOT is_holdout)                     AS treated_rev_per_cust,
    avg(revenue) FILTER (WHERE is_holdout)                         AS holdout_rev_per_cust
FROM attributed
GROUP BY campaign_id, campaign_name, campaign_type, channel, brand_id;

CREATE UNIQUE INDEX ON mv_campaign (campaign_id);

ANALYZE mv_customer;
ANALYZE mv_monthly;
ANALYZE mv_cohort;
ANALYZE mv_campaign;
