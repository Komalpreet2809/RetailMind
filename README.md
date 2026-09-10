---
title: RetailMind
emoji: 🛍️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: A 9.4M-row retail warehouse that shows its query plans
---

# RetailMind

A retail customer analytics warehouse — **9.4M orders, 300k customers, three years** of
Postgres — where the SQL is on show. Every number in the dashboard opens to reveal the
query that produced it, and a **Query Lab** documents the five queries that were too slow
at nine million rows, what the planner was doing wrong, and what fixed them.

Built around the questions a retail CEO actually asks: *why are customers leaving, which
ones should we target, and which campaigns actually made money?*

---

## Why this exists

Most analytics projects hide their SQL and run on datasets small enough that query
performance never matters. On 50k rows every query is fast, even a badly written one —
so nothing is learned and nothing is proved.

This one is deliberately large enough to hurt. Building it, three dashboard queries took
6–9 seconds each, a correlated subquery took 1.4 seconds, and a missing index turned a
simple join into a full-table hash build. All of that is documented rather than quietly
fixed.

## The five pages

| Page | Question it answers |
|---|---|
| **Overview** | Revenue, orders, AOV, repeat rate, CLV, seasonality, channel mix |
| **Segments** | RFM quintile scoring — Champions, Loyal, At Risk, Lost, and what to do about each |
| **Retention** | Cohort heatmap: who comes back, and does the acquisition month predict it |
| **Campaigns** | Treated vs holdout, so the answer is incremental revenue rather than response rate |
| **Query Lab** | Five slow queries, their plans, the diagnosis, and the fix |

## Query Lab results

Measured against 9.4M orders, median of 3 runs, warm cache on both sides. The "before"
state is produced by genuinely dropping the index — not by hinting the planner away from
it — so the plans shown are what Postgres actually chose.

| Query | Before | After | Gain | The lesson |
|---|---|---|---|---|
| Each customer's most recent order | 1,360 ms | 38 ms | **35×** | Correlated subquery → `DISTINCT ON` |
| Brand revenue for a date range | 133 ms | 19 ms | **7×** | Composite index, equality column first |
| Revenue for a single month | 348 ms | 52 ms | **7×** | `extract()` on a column makes it non-sargable |
| Platinum customers in a city | 176 ms | 48 ms | **4×** | Postgres does not index foreign keys for you |
| One month out of three years | 83 ms | 46 ms | **2×** | Range partitioning, pruned at plan time |

Plus the dashboard itself: aggregating 9.4M orders on every page load cost **~26 seconds
across the five pages**. Materialized rollups brought that to **401 ms** — a 65× cut — by
not recomputing history that cannot change.

## What the data does

Synthetic, but not random. Uniform-random orders give flat cohort curves and a meaningless
RFM split, so customers here carry latent traits and their orders fall out of those:

- **Heavy-tailed value** — the top 20% of customers drive 80.6% of revenue
- **A long single-visit tail** — 21.9% of customers bought exactly once
- **Per-customer lapse** — retention decays instead of flatlining
- **Festive seasonality** — Diwali and end-of-season sale peaks
- **Campaigns with real holdouts** — treated customers genuinely receive incremental
  orders, and two campaign types are deliberately given near-zero lift

That last one is what makes the campaign page worth reading: win-back campaigns open at
44% and convert 7.10% against a holdout of 6.81%. A **0.29pp lift** — they have been taking
credit for orders that were already coming.

## Running it

```bash
docker compose up -d                      # Postgres 16 on :5433
pip install -r requirements.txt

python scripts/generate.py                # schema + 9.4M rows, ~2 min
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
app/pages/               the five pages
```

## Stack

PostgreSQL 16 · Python · Streamlit · Plotly · Docker

---

Built by [Komalpreet Kaur](https://komalpreet.me) · [GitHub](https://github.com/Komalpreet2809)
