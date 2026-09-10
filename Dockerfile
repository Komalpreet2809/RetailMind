# RetailMind :: Postgres + Streamlit in a single container, for Hugging Face Spaces.
#
# The warehouse is generated at BUILD time, not at startup. Nine million rows take
# a few minutes to produce, and a Space that spent four minutes generating data on
# every cold start would be useless to anyone clicking a link. Baking the finished
# cluster into an image layer instead means the container starts in seconds.
#
# Postgres refuses to run as root, and Spaces run as uid 1000, so the whole
# cluster lives under that user and PGDATA sits in the home directory.
#
# The Postgres major version is deliberately not pinned in a path: the base image
# tracks Debian, and Debian's default Postgres moves (this picked up 17 when the
# python:3.11-slim base moved to trixie). Symlinking whatever got installed keeps
# initdb and pg_ctl on PATH regardless.

FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PGDATA=/home/user/pgdata \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        postgresql postgresql-contrib libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/lib/postgresql/*/bin/* /usr/local/bin/

RUN useradd -m -u 1000 user
WORKDIR /home/user/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user:user app/     ./app/
COPY --chown=user:user sql/     ./sql/
COPY --chown=user:user scripts/ ./scripts/
COPY --chown=user:user docker/  ./docker/
RUN chmod +x docker/*.sh \
    && mkdir -p /home/user/app/data \
    && chown -R user:user /home/user

USER user

# Build the warehouse into the image. Overridable at build time:
#   docker build --build-arg RM_ORDERS=2000000 --build-arg RM_CUSTOMERS=80000 .
ARG RM_ORDERS=10000000
ARG RM_CUSTOMERS=300000
RUN RM_ORDERS=${RM_ORDERS} RM_CUSTOMERS=${RM_CUSTOMERS} ./docker/build-warehouse.sh

EXPOSE 7860
CMD ["./docker/start.sh"]
