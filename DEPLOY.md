# Deploying RetailMind

**Streamlit Community Cloud** for the app, **Neon** for the database. Both free,
both permanent, both sign in with GitHub.

> A note on the Dockerfile in this repo: it builds Postgres and Streamlit into a
> single image with the warehouse baked in at build time, which was the original
> deployment target. Hugging Face moved Docker Spaces behind a paid plan in July
> 2026, so it is no longer the hosted path — but it is still the fastest way to
> stand the whole project up locally, and `docker run -p 7860:7860` gives you the
> full ~9M-row build with nothing else installed.

---

## 1. Database — Neon

Create a project at [neon.tech](https://neon.tech). Postgres 17, any US region
(Streamlit Cloud runs in the US, and the hop that matters is app→database).

Take the **direct** connection string, not the pooled one — the pooled endpoint
goes through PgBouncer, which breaks `COPY` and session-level settings that bulk
loading needs. The direct hostname is the pooled one with `-pooler` removed.

```bash
export RETAILMIND_DSN="postgresql://user:pass@ep-xxxx.us-east-2.aws.neon.tech/neondb?sslmode=require"

RM_ORDERS=3500000 RM_CUSTOMERS=110000 python scripts/generate.py
psql "$RETAILMIND_DSN" -f sql/05_rollups.sql
python scripts/benchmark.py
```

**On sizing.** The free tier is 0.5 GB. A ~9M-order build is ~1.8 GB, so the
hosted copy runs ~3.3M orders and omits `sql/04_partition.sql` — the partitioned
copy of the fact table would double storage for one demonstration. The Query Lab
detects its absence and says so rather than offering a button that fails.

The full-scale numbers are kept in `data/benchmarks_local.json` and shown beside
the hosted ones, so the page reports both scales instead of quietly presenting
the smaller one.

## 2. App — Streamlit Community Cloud

Push to GitHub first:

```bash
gh repo create RetailMind --public --source=. --remote=origin --push
```

Then at [share.streamlit.io](https://share.streamlit.io):

| Field | Value |
|---|---|
| Repository | `Komalpreet2809/RetailMind` |
| Branch | `main` |
| Main file path | `app/main.py` |

Under **Advanced settings → Secrets**, paste:

```toml
RETAILMIND_DSN = "postgresql://user:pass@ep-xxxx.us-east-2.aws.neon.tech/neondb?sslmode=require"
```

`app/db.py` reads the environment variable first and falls back to
`st.secrets`, so the same code runs locally against Docker and hosted against
Neon with nothing to change.

## 3. Two things to expect

**Neon suspends when idle.** The first request after a quiet spell waits a few
seconds for the compute to wake. Normal speed after that.

**Streamlit Cloud sleeps too.** Free apps idle out after inactivity and wake on
visit. Nothing is lost; the first visitor of the day waits a little.

---

## Rebuilding locally

```bash
docker compose up -d
python scripts/generate.py
docker exec -i retailmind-db psql -U retail -d retailmind -q -f - < sql/04_partition.sql
docker exec -i retailmind-db psql -U retail -d retailmind -q -f - < sql/05_rollups.sql
python scripts/benchmark.py      # -> data/benchmarks.json
python scripts/scaling.py        # -> data/scaling.json  (15-20 min, rebuilds 4x)
```

## Everything in one container

```bash
docker build -t retailmind .
docker run --rm -p 7860:7860 retailmind
# http://localhost:7860 -- the full build, no external database
```
