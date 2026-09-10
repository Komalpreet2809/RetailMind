-- RetailMind :: partitioned copy of the fact table
--
-- Range-partitioned by month across the three-year window. Two things this buys
-- that an index on order_date does not:
--
--   1. Partition pruning happens at plan time. A query for one month is planned
--      against one partition; the other 35 are never opened. The plan itself
--      says so ("Partitions removed by pruning: 35"), which an index scan over a
--      single large heap can never claim.
--   2. Dropping a month of history becomes DROP TABLE -- instant, no bloat, no
--      vacuum afterwards. On a retail warehouse with a retention policy that is
--      usually the reason partitioning gets adopted at all.
--
-- The cost is real and worth stating: 36 tables to maintain, every unique
-- constraint must carry the partition key, and a query with no date predicate is
-- now slower because it scans all 36 partitions instead of one heap.

DROP TABLE IF EXISTS orders_part CASCADE;

CREATE TABLE orders_part (
    order_id    bigint    NOT NULL,
    customer_id integer   NOT NULL,
    store_id    smallint  NOT NULL,
    brand_id    smallint  NOT NULL,
    order_date  date      NOT NULL,
    channel     text      NOT NULL,
    items       smallint  NOT NULL,
    amount      numeric(10,2) NOT NULL
) PARTITION BY RANGE (order_date);

-- One partition per month, 2023-01 .. 2025-12.
DO $$
DECLARE
    m date := DATE '2023-01-01';
BEGIN
    WHILE m < DATE '2026-01-01' LOOP
        EXECUTE format(
            'CREATE TABLE %I PARTITION OF orders_part FOR VALUES FROM (%L) TO (%L)',
            'orders_p' || to_char(m, 'YYYY_MM'), m, m + INTERVAL '1 month'
        );
        m := m + INTERVAL '1 month';
    END LOOP;
END $$;

INSERT INTO orders_part
SELECT order_id, customer_id, store_id, brand_id, order_date, channel, items, amount
FROM orders;

ANALYZE orders_part;
