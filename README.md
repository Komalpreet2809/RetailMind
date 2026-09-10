<img src="app/static/logo.svg" width="66" alt="RetailMind">

# RetailMind

**[Live demo](https://retailmind-komalpreet.streamlit.app)** · [Query Lab](https://retailmind-komalpreet.streamlit.app/Query_Lab)

A retail customer analytics warehouse — **8.9M orders, 300k customers, three years** of
Postgres — where the SQL is on show. Every number in the dashboard opens to reveal the
query that produced it, and a **Query Lab** documents the five queries that were too slow
at that size, what the planner was doing wrong, and what fixed them.

Built around the questions a retail CEO actually asks: *why are customers leaving, which
ones should we target, and which campaigns actually made money?*

---

## Why this exists

Most analytics projects hide their SQL and run on datasets small enough that query
performance never matters. On 50k rows every query is fast, even a badly written one —
so nothing is learned and nothing is proved.

This one is deliberately large enough to hurt. Building it, three dashboard queries took
6–9 seconds each, a correlated subquery took 2.2 seconds, and a missing index turned a
simple join into a full-table hash build. All of that is documented rather than quietly
fixed.

## The pages

| Page | Question it answers |
|---|---|
| **Overview** | Revenue, orders, AOV, repeat rate, CLV, seasonality, channel mix |
| **Segments** | RFM quintile scoring — Champions, Loyal, At Risk, Lost, and what to do about each |
| **Retention** | Cohort heatmap: who comes back, and does the acquisition month predict it |
| **Campaigns** | Treated vs holdout, so the answer is incremental revenue rather than response rate |
| **Query Lab** | Five slow queries, their plans, the diagnosis, the fix, and how each scales |
| **Plan Doctor** | Paste any SELECT — it runs EXPLAIN ANALYZE and reports what is wrong |

## Query Lab results

Measured against 8,880,833 orders, median of 3 runs, warm cache on
both sides. Timing is the server's own reported execution time from `EXPLAIN ANALYZE`, not
client wall clock — against a managed database on another continent the round trip alone is
~200ms and would bury every result in latency. The "before" state is produced by genuinely
dropping the index, not by hinting the planner away from it, so the plans shown are what
Postgres actually chose.

The [live demo](https://retailmind-komalpreet.streamlit.app) runs a smaller 3,281,497-order
copy on a free 0.5 GB tier and re-runs the same suite there (6,793 ms →
85 ms on the worst offender, 80×).
Both sets are shown in the app, side by side and labelled — they differ by hardware as well
as row count, so the pair is not a scaling curve and the page says so.

| Query | Before | After | Gain | The lesson |
|---|---|---|---|---|
| Each customer's most recent order | 2,174 ms | 42 ms | **52x** | Correlated subquery -> `DISTINCT ON` |
| Revenue for a single month | 362 ms | 51 ms | **7x** | `extract()` on a column makes it non-sargable |
| Top spenders in a city | 301 ms | 60 ms | **5x** | Postgres does not index foreign keys for you |
| Brand revenue for a date range | 128 ms | 23 ms | **6x** | Composite index, equality column first |
| One month out of three years | 98 ms | 59 ms | **2x** | Range partitioning, pruned at plan time |

Plus the dashboard itself: aggregating 8.9M orders on every page load cost **~26 seconds
across the five dashboard pages**. Materialized rollups brought that to **401 ms** — a 65× cut — by
not recomputing history that cannot change.


## How they behave as the table grows

The table above is a single before/after. This is the more useful experiment:
one machine, one build, four warehouse sizes, only the row count changing.

| Query | 99k rows | 8.9M rows | Growth | After the fix |
|---|---|---|---|---|
| Brand revenue for a date range | 3 ms | 136 ms | **39x** | 0 -> 21 ms |
| Each customer's most recent order | 560 ms | 2,227 ms | **4x** | 17 -> 42 ms |
| Top spenders in a city | 9 ms | 314 ms | **37x** | 1 -> 58 ms |
| Revenue for a single month | 12 ms | 362 ms | **30x** | 1 -> 50 ms |

The data grew **90x** across those builds. Three of the four
queries grew 30-40x with it — and the part that matters is where they started: 3ms,
9ms, 12ms. Nobody notices a 3ms query in review. Those are the ones that ship and
then take a dashboard down a year later once the table has caught up.

The correlated subquery is the exception, and the more interesting case: it grew
only 4x because it was **already slow at 99,000 rows**. Its cost is set by how many
times the subquery executes, which barely moves with table size — so it is the one
bad query you would actually catch in development. The other three hide until
production.

After the fix, every one of them is close to flat. That is the objective: cost that
tracks the rows returned rather than the rows stored.

## What the data does

Synthetic, but not random. Uniform-random orders give flat cohort curves and a meaningless
RFM split, so customers here carry latent traits and their orders fall out of those:

- **Heavy-tailed value** — the top 20% of customers drive 83.1% of revenue
- **A long single-visit tail** — 9.9% of customers bought exactly once
- **Per-customer lapse** — retention decays instead of flatlining
- **Festive seasonality** — Diwali and end-of-season sale peaks
- **Campaigns with real holdouts** — treated customers genuinely receive incremental
  orders, and two campaign types are deliberately given near-zero lift

That last one is what makes the campaign page worth reading: win-back campaigns have the
second-highest open rate at **44%** and convert **27.65%** against a holdout of **27.91%** —
a lift of **−0.26pp**, which is to say none at all. They have been taking credit for orders
that were already coming, while loyalty offers clear their control by **5.9pp**.

## Running it

```bash
docker compose up -d                      # Postgres 16 on :5433
pip install -r requirements.txt

python scripts/generate.py                # schema + ~8.9M rows, ~2 min
docker exec -i retailmind-db psql -U retail -d retailmind -f - < sql/04_partition.sql
docker exec -i retailmind-db psql -U retail -d retailmind -f - < sql/05_rollups.sql
python scripts/benchmark.py               # regenerates data/benchmarks.json

streamlit run app/main.py
```

Dataset size is configurable: `RM_ORDERS=2000000 RM_CUSTOMERS=80000 python scripts/generate.py`.

## Layout

```
sql/01_schema.sql        tables, deliberately with no indexes beyond primary keys
sql/04_partition.sql     monthly range-partitioned copy of the fact table
sql/05_rollups.sql       materialized views behind the dashboard
scripts/generate.py      behavioural data generator
scripts/benchmark.py     Query Lab harness — drops the fix, measures, applies it, measures
app/queries.py           every query the dashboard runs, kept in one readable place
app/views/               the six pages
app/plandoc.py           plan-analysis rules behind the Plan Doctor
scripts/scaling.py       the same queries measured at four warehouse sizes
```

## Stack

PostgreSQL 16/17 · Python · Streamlit · Plotly · Docker · Neon

---

Built by [Komalpreet Kaur](https://komalpreet.me) · [GitHub](https://github.com/Komalpreet2809)
