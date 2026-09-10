"""
RetailMind :: Query Lab benchmark harness

Runs each slow/fast pair against the real warehouse, captures the planner output
for both, and writes data/benchmarks.json for the app to render.

Method, so the numbers mean something:
  * the "before" state is produced by actually dropping the index, not by hinting
    the planner away from it -- what you see is what Postgres genuinely chose
  * every query runs REPEATS times and the median is reported, so one unlucky
    run doesn't set the headline number
  * a warm-up run precedes timing on both sides, so this compares warm cache to
    warm cache. Cold-cache numbers would look far more dramatic and would be
    much less honest.
"""

import json
import os
import statistics
import sys
import time
import psycopg2

DSN = os.environ.get(
    "RETAILMIND_DSN", "postgresql://retail:retail@localhost:5433/retailmind"
)
REPEATS = 3
# Overridable so a local run does not clobber the hosted results, which are the
# ones the deployed app reads.
OUT = os.environ.get(
    "RM_BENCH_OUT",
    os.path.join(os.path.dirname(__file__), "..", "data", "benchmarks.json"),
)


PAIRS = [
    {
        "id": "composite_index",
        "title": "Brand revenue for a date range",
        "question": "What did Fabrique sell during the Diwali window?",
        "lesson": "Composite index, equality column first",
        "diagnosis": (
            "With no usable index Postgres has one option: read every row in the "
            "table and throw away almost all of them. The filter is an equality on brand_id plus a "
            "range on order_date, so a composite index on (brand_id, order_date) "
            "lets it seek straight to the matching slice. Column order matters -- "
            "equality first, range second. Reversed, the index can still be used "
            "but has to scan every brand inside the date range."
        ),
        # idx_orders_date has to go too: a bare date index would give the planner
        # a bitmap scan and the "before" state would no longer be a clean
        # sequential scan of the whole table.
        "drop": [
            "DROP INDEX IF EXISTS idx_orders_brand_date",
            "DROP INDEX IF EXISTS idx_orders_date",
        ],
        "create": ["CREATE INDEX idx_orders_brand_date ON orders (brand_id, order_date)"],
        "slow": """
            SELECT count(*) AS orders, round(sum(amount)) AS revenue
            FROM orders
            WHERE brand_id = 3
              AND order_date BETWEEN DATE '2025-10-01' AND DATE '2025-11-30'
        """,
        "fast": """
            SELECT count(*) AS orders, round(sum(amount)) AS revenue
            FROM orders
            WHERE brand_id = 3
              AND order_date BETWEEN DATE '2025-10-01' AND DATE '2025-11-30'
        """,
    },
    {
        "id": "correlated_subquery",
        "title": "Each customer's most recent order",
        "question": "What did each customer buy the last time they came in?",
        "lesson": "Per-row correlated subquery to a single ordered pass",
        "diagnosis": (
            "The subquery is correlated: it re-runs for every candidate row to ask "
            "'is this the customer's latest order?'. Work scales with the number of "
            "order rows, not the number of customers -- the same shape as an N+1 "
            "query in application code, and it stays slow even with the index in "
            "place because the problem is how often it runs, not how fast each run "
            "is. DISTINCT ON answers the same question in one pass: sort by "
            "customer then date descending, keep the first row per customer. Note "
            "both sides here have the index available -- this pair is purely about "
            "query shape."
        ),
        "drop": [],
        "create": ["CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders (customer_id)"],
        "index_first": True,
        "slow": """
            SELECT o.customer_id, o.order_id, o.order_date, o.amount
            FROM orders o
            WHERE o.customer_id <= 5000
              AND o.order_date = (
                    SELECT max(o2.order_date)
                    FROM orders o2
                    WHERE o2.customer_id = o.customer_id
              )
        """,
        "fast": """
            SELECT DISTINCT ON (o.customer_id)
                   o.customer_id, o.order_id, o.order_date, o.amount
            FROM orders o
            WHERE o.customer_id <= 5000
            ORDER BY o.customer_id, o.order_date DESC
        """,
    },
    {
        "id": "unindexed_join",
        "title": "Top spenders in a city",
        "question": "Who are our platinum-tier customers in Bengaluru?",
        "lesson": "Postgres does not index foreign keys for you",
        "diagnosis": (
            "customer_id is a foreign key in every meaningful sense, but Postgres "
            "creates an index only for the primary key and unique constraints -- "
            "never for the referencing side. Without it, joining a few thousand "
            "platinum Bengaluru customers to the fact table forces a full scan and a hash "
            "build over the entire table. With the index the planner switches to a "
            "nested loop that touches only the matching orders."
        ),
        "drop": ["DROP INDEX IF EXISTS idx_orders_customer"],
        "create": ["CREATE INDEX idx_orders_customer ON orders (customer_id)"],
        "slow": """
            SELECT c.customer_id, c.loyalty_tier,
                   count(*) AS orders, round(sum(o.amount)) AS spend
            FROM customers c
            JOIN orders o ON o.customer_id = c.customer_id
            WHERE c.city = 'Bengaluru'
              AND c.loyalty_tier = 'platinum'
            GROUP BY c.customer_id, c.loyalty_tier
            ORDER BY spend DESC
            LIMIT 20
        """,
        "fast": """
            SELECT c.customer_id, c.loyalty_tier,
                   count(*) AS orders, round(sum(o.amount)) AS spend
            FROM customers c
            JOIN orders o ON o.customer_id = c.customer_id
            WHERE c.city = 'Bengaluru'
              AND c.loyalty_tier = 'platinum'
            GROUP BY c.customer_id, c.loyalty_tier
            ORDER BY spend DESC
            LIMIT 20
        """,
    },
    {
        "id": "sargable",
        "title": "Revenue for a single month",
        "question": "What was November 2025 revenue?",
        "lesson": "A function on an indexed column throws the index away",
        "diagnosis": (
            "extract(year from order_date) has to be evaluated for every row before "
            "the filter can be applied, so the index on order_date is unusable and "
            "Postgres falls back to a full scan. Rewriting the same condition as a "
            "half-open range on the bare column makes it sargable -- the planner can "
            "seek to the start of November and stop at the start of December. Identical "
            "result, completely different plan."
        ),
        "drop": [],
        "create": ["CREATE INDEX IF NOT EXISTS idx_orders_date ON orders (order_date)"],
        "slow": """
            SELECT count(*) AS orders, round(sum(amount)) AS revenue
            FROM orders
            WHERE extract(year from order_date) = 2025
              AND extract(month from order_date) = 11
        """,
        "fast": """
            SELECT count(*) AS orders, round(sum(amount)) AS revenue
            FROM orders
            WHERE order_date >= DATE '2025-11-01'
              AND order_date <  DATE '2025-12-01'
        """,
        "index_first": True,
    },
    {
        "id": "partition_pruning",
        "title": "One month out of three years",
        "question": "How did November 2025 trade?",
        "lesson": "Range partitioning by month, pruned at plan time",
        "diagnosis": (
            "This pair is deliberately a fair fight: the unpartitioned table keeps "
            "its index on order_date, so the 'before' side is already getting a "
            "bitmap scan rather than a full scan. What partitioning adds is "
            "elimination at plan time -- the planner reads the month from the "
            "predicate, resolves it to one partition, and never opens the other 35. "
            "The plan says 'Partitions removed by pruning: 35'. Expect a solid win "
            "rather than an enormous one, and be honest about why you would still "
            "do it: dropping a month of history becomes DROP TABLE instead of a "
            "mass DELETE followed by a vacuum, and each partition's statistics and "
            "indexes stay small enough to matter. The cost is that any query "
            "without a date predicate now has to touch all 36 partitions."
        ),
        "drop": [],
        "create": ["CREATE INDEX IF NOT EXISTS idx_orders_date ON orders (order_date)"],
        "index_first": True,
        "slow": """
            SELECT count(*) AS orders, round(sum(amount)) AS revenue,
                   count(DISTINCT customer_id) AS customers
            FROM orders
            WHERE order_date >= DATE '2025-11-01'
              AND order_date <  DATE '2025-12-01'
        """,
        "fast": """
            SELECT count(*) AS orders, round(sum(amount)) AS revenue,
                   count(DISTINCT customer_id) AS customers
            FROM orders_part
            WHERE order_date >= DATE '2025-11-01'
              AND order_date <  DATE '2025-12-01'
        """,
    },
]


def explain(cur, sql):
    cur.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " + sql)
    return "\n".join(r[0] for r in cur.fetchall())


def _server_ms(cur, sql):
    """
    Execution time as the server reports it, not as the client experiences it.

    Wall-clock timing from the client includes the network round trip, which is
    a millisecond against a local container and ~200ms against a managed database
    on another continent. Measured that way every query on the hosted database
    would land between 200 and 250ms and the entire before/after contrast would
    disappear into the latency. EXPLAIN ANALYZE reports what the query actually
    cost inside Postgres, which is the thing being compared, and it makes the
    local and hosted runs directly comparable.

    The instrumentation is not free -- it inflates row-heavy plans somewhat --
    but it inflates both sides of every comparison equally.
    """
    cur.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + sql)
    plan = cur.fetchone()[0]
    return float(plan[0]["Execution Time"])


def timed(cur, sql, repeats=REPEATS):
    _server_ms(cur, sql)          # warm-up, not recorded
    times = [_server_ms(cur, sql) for _ in range(repeats)]
    return statistics.median(times), min(times)


def run_pair(cur, p):
    print(f"\n  {p['id']}")

    # --- before: make sure the fix is absent, then measure what the planner does
    if not p.get("index_first"):
        for stmt in p["drop"]:
            cur.execute(stmt)
    else:
        # This pair is about query shape, not a missing index: the index exists
        # in both states and the slow query simply cannot use it.
        for stmt in p["create"]:
            cur.execute(stmt)
    cur.execute("ANALYZE orders")

    slow_plan = explain(cur, p["slow"])
    slow_ms, slow_best = timed(cur, p["slow"])
    print(f"    before  {slow_ms:9.1f} ms")

    # --- after
    for stmt in p["create"]:
        cur.execute(stmt)
    cur.execute("ANALYZE orders")

    fast_plan = explain(cur, p["fast"])
    fast_ms, fast_best = timed(cur, p["fast"])
    print(f"    after   {fast_ms:9.1f} ms   ({slow_ms / max(fast_ms, 1e-9):.0f}x)")

    return {
        **{k: p[k] for k in ("id", "title", "question", "lesson", "diagnosis")},
        "slow_sql": p["slow"].strip(),
        "fast_sql": p["fast"].strip(),
        "fix_sql": "; ".join(p["create"]) or "(query rewrite only)",
        "slow_ms": round(slow_ms, 2),
        "fast_ms": round(fast_ms, 2),
        "speedup": round(slow_ms / max(fast_ms, 1e-9), 1),
        "slow_plan": slow_plan,
        "fast_plan": fast_plan,
    }


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("SELECT count(*) FROM orders")
    n = cur.fetchone()[0]
    print(f"\nQuery Lab :: {n:,} orders\n" + "-" * 46)

    # The hosted database omits the partitioned copy of the fact table -- it
    # would double storage on a 0.5 GB tier for a single demonstration. Skip any
    # pair whose tables are not present rather than failing the whole run, and
    # record what was skipped so the page can say so instead of showing a gap.
    def available(p):
        for tbl in ("orders_part",):
            if tbl in p["slow"] + p["fast"]:
                cur.execute("SELECT to_regclass(%s) IS NOT NULL", (tbl,))
                if not cur.fetchone()[0]:
                    print(f"\n  {p['id']}: skipped, {tbl} not present here")
                    return False
        return True

    runnable = [p for p in PAIRS if available(p)]
    skipped = [p["id"] for p in PAIRS if p not in runnable]
    results = [run_pair(cur, p) for p in runnable]

    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "order_count": n,
        "repeats": REPEATS,
        "skipped": skipped,
        "results": results,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(payload, f, indent=2)

    print("\n" + "-" * 46)
    for r in results:
        print(f"  {r['id']:22s} {r['slow_ms']:9.1f} -> {r['fast_ms']:8.1f} ms  {r['speedup']:6.0f}x")
    print(f"\n  wrote {OUT}\n")

    cur.close()
    conn.close()


if __name__ == "__main__":
    sys.exit(main())
