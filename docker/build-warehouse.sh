#!/usr/bin/env bash
# Generate the whole warehouse during docker build so the Space starts instantly.
set -euo pipefail

echo "==> initdb"
initdb -D "$PGDATA" -U retail --auth=trust --encoding=UTF8 >/dev/null

# Build-time tuning. These are generous because nothing else is running during
# the build; start.sh resets them to values that suit a small shared container.
cat >> "$PGDATA/postgresql.conf" <<'CONF'
shared_buffers = 512MB
work_mem = 32MB
maintenance_work_mem = 512MB
random_page_cost = 1.1
track_io_timing = on
fsync = off
synchronous_commit = off
full_page_writes = off
# WAL settings matter here for image size, not for speed. A bulk load of 9.4M
# rows with a 4GB max_wal_size leaves ~2GB of preallocated WAL segments sitting
# in the baked image -- larger than the data itself. minimal WAL emits far less
# during COPY, and a small max_wal_size lets checkpoints recycle it away.
wal_level = minimal
max_wal_senders = 0
max_wal_size = 1GB
min_wal_size = 80MB
CONF

echo "==> start postgres"
pg_ctl -D "$PGDATA" -o "-c listen_addresses='' -c unix_socket_directories=/tmp" -w start

export RETAILMIND_DSN="postgresql://retail@/retailmind?host=/tmp"
createdb -h /tmp -U retail retailmind

echo "==> generate ${RM_ORDERS:-9400000} orders"
python scripts/generate.py

echo "==> partitioned copy"
psql -h /tmp -U retail -d retailmind -q -f sql/04_partition.sql

echo "==> rollups"
psql -h /tmp -U retail -d retailmind -q -f sql/05_rollups.sql

echo "==> benchmarks"
python scripts/benchmark.py

echo "==> vacuum + analyze"
psql -h /tmp -U retail -d retailmind -q -c "VACUUM (ANALYZE);"

psql -h /tmp -U retail -d retailmind -tAc \
  "SELECT 'orders: '||count(*) FROM orders" || true

# Two checkpoints before shutdown: the first flushes, the second lets Postgres
# recycle the now-surplus WAL segments instead of baking them into the image.
echo "==> checkpoint"
psql -h /tmp -U retail -d retailmind -q -c "CHECKPOINT;"
psql -h /tmp -U retail -d retailmind -q -c "CHECKPOINT;"

echo "==> stop postgres"
pg_ctl -D "$PGDATA" -m fast -w stop

# Durability was off for speed during the build; the shipped cluster gets it back.
sed -i 's/^fsync = off/fsync = on/;s/^synchronous_commit = off/synchronous_commit = on/;s/^full_page_writes = off/full_page_writes = on/' "$PGDATA/postgresql.conf"

echo "==> warehouse baked, $(du -sh "$PGDATA" | cut -f1)"
