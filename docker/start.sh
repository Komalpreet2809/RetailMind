#!/usr/bin/env bash
# Runtime entrypoint: bring up the baked cluster, then serve the app on 7860.
set -euo pipefail

# A free Space is small and shared, so the build-time memory settings would be
# reckless here. Trim them before starting.
sed -i 's/^shared_buffers = .*/shared_buffers = 256MB/;s/^work_mem = .*/work_mem = 16MB/;s/^maintenance_work_mem = .*/maintenance_work_mem = 128MB/' "$PGDATA/postgresql.conf"

pg_ctl -D "$PGDATA" -o "-c listen_addresses='' -c unix_socket_directories=/tmp" -w start

export RETAILMIND_DSN="postgresql://retail@/retailmind?host=/tmp"

exec streamlit run app/main.py \
    --server.port 7860 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false
