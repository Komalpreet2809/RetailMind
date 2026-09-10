"""
RetailMind :: how the same query behaves as the table grows.

The job description this project was built against asks for one thing above all:
work out why a query that runs fine on a small dataset falls over at scale. A
single before/after at one row count cannot show that. This does.

Each query is run at four warehouse sizes. What comes out is the shape of the
curve, which is the part that actually matters:

  * a query whose cost is O(rows) climbs steadily and predictably
  * a query the planner can satisfy from an index stays almost flat -- the whole
    point of an index is that cost tracks the rows you return, not the rows you
    store
  * a correlated subquery climbs faster than the data does, because the number of
    executions grows with the table as well as the cost of each one

That last shape is the one worth recognising on sight. It is the query that looks
perfectly healthy in development and takes the dashboard down in production.

Warning: this rebuilds the warehouse four times and takes 15-20 minutes. It
leaves the database at full size with partitions, rollups and indexes intact.
"""

import json
import os
import subprocess
import sys
import time

import psycopg2

sys.path.insert(0, os.path.dirname(__file__))
import benchmark as bm  # noqa: E402

DSN = os.environ.get(
    "RETAILMIND_DSN", "postgresql://retail:retail@localhost:5433/retailmind"
)
ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "data", "scaling.json")

# Customers are scaled with orders so orders-per-customer stays roughly constant.
# Without that, the small builds would have the same 300k customers sharing far
# fewer orders and the curve would measure two things changing at once.
SIZES = [
    (100_000, 8_000),
    (500_000, 30_000),
    (2_000_000, 90_000),
    (9_400_000, 300_000),
]

# The partitioned pair needs a second physical table built at every size, which
# roughly doubles the run time for one extra line on the chart.
SKIP = {"partition_pruning"}


def psql(path):
    subprocess.run(
        ["docker", "exec", "-i", "retailmind-db", "psql", "-U", "retail",
         "-d", "retailmind", "-q", "-f", "-"],
        stdin=open(os.path.join(ROOT, path)), check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def build(orders, customers):
    env = {**os.environ, "RM_ORDERS": str(orders), "RM_CUSTOMERS": str(customers)}
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "generate.py")],
                   env=env, check=True, stdout=subprocess.DEVNULL)
    psql("sql/05_rollups.sql")


def measure(cur):
    out = {}
    for p in bm.PAIRS:
        if p["id"] in SKIP:
            continue
        if not p.get("index_first"):
            for stmt in p["drop"]:
                cur.execute(stmt)
        else:
            for stmt in p["create"]:
                cur.execute(stmt)
        cur.execute("ANALYZE orders")
        slow, _ = bm.timed(cur, p["slow"], repeats=3)

        for stmt in p["create"]:
            cur.execute(stmt)
        cur.execute("ANALYZE orders")
        fast, _ = bm.timed(cur, p["fast"], repeats=3)

        out[p["id"]] = {"slow_ms": round(slow, 2), "fast_ms": round(fast, 2)}
        print(f"      {p['id']:22s} {slow:9.1f} -> {fast:8.1f} ms")
    return out


def main():
    t0 = time.time()
    points = []

    for orders, customers in SIZES:
        print(f"\n  building {orders:,} orders / {customers:,} customers")
        build(orders, customers)

        conn = psycopg2.connect(DSN)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM orders")
        actual = cur.fetchone()[0]
        print(f"    measuring at {actual:,}")
        points.append({"orders": actual, "customers": customers, "results": measure(cur)})
        cur.close()
        conn.close()

    # Leave the database in its full, complete state.
    print("\n  restoring full build (partitions + rollups + benchmarks)")
    psql("sql/04_partition.sql")
    psql("sql/05_rollups.sql")
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "benchmark.py")],
                   check=True, stdout=subprocess.DEVNULL)

    labels = {p["id"]: {"title": p["title"], "lesson": p["lesson"]}
              for p in bm.PAIRS if p["id"] not in SKIP}
    with open(OUT, "w") as f:
        json.dump({"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "labels": labels, "points": points}, f, indent=2)

    print(f"\n  done in {time.time() - t0:.0f}s -> {OUT}\n")
    hdr = "  " + "query".ljust(24) + "".join(f"{p['orders']:>13,}" for p in points)
    print(hdr)
    for qid in labels:
        row = "  " + qid.ljust(24)
        for p in points:
            r = p["results"].get(qid)
            row += f"{r['slow_ms']:>13,.0f}" if r else " " * 13
        print(row)


if __name__ == "__main__":
    sys.exit(main())
