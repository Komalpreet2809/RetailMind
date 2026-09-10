"""Connection handling and the query helpers every page uses."""

import os
import re
import time
import pandas as pd
import psycopg2
import streamlit as st

DEFAULT_DSN = "postgresql://retail:retail@localhost:5433/retailmind"


def dsn():
    """Local env var first, Streamlit secrets when deployed."""
    if os.environ.get("RETAILMIND_DSN"):
        return os.environ["RETAILMIND_DSN"]
    try:
        return st.secrets["RETAILMIND_DSN"]
    except Exception:
        return DEFAULT_DSN


@st.cache_resource(show_spinner=False)
def _conn():
    c = psycopg2.connect(dsn())
    c.autocommit = True
    return c


def _reconnect():
    _conn.clear()
    return _conn()


@st.cache_data(ttl=900, show_spinner=False)
def run(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Run a query, returning a DataFrame. Timing is stashed for the SQL panel."""
    for attempt in (1, 2):
        try:
            conn = _conn()
            t = time.perf_counter()
            df = pd.read_sql_query(sql, conn, params=params)
            df.attrs["elapsed_ms"] = (time.perf_counter() - t) * 1000.0
            return df
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            if attempt == 2:
                raise
            _reconnect()  # connection went stale between reruns


@st.cache_data(ttl=3600, show_spinner=False)
def table_exists(name: str) -> bool:
    """
    The hosted database is a 0.5 GB free tier and omits the partitioned copy of
    the fact table, which would double storage for one demo. Pages check before
    offering to run anything against it.
    """
    return bool(run("SELECT to_regclass(%(n)s) IS NOT NULL AS ok", {"n": name}).iloc[0]["ok"])


def explain(sql: str, params: dict | None = None) -> str:
    conn = _conn()
    with conn.cursor() as cur:
        cur.execute("EXPLAIN (ANALYZE, BUFFERS) " + sql, params)
        return "\n".join(r[0] for r in cur.fetchall())


# ----------------------------------------------------------------------------- safe explain
# The Plan Doctor page runs SQL typed by whoever is looking at the site, against a
# live database whose role owns every table in it. Three layers stand between a
# visitor and damage, because any one of them alone is a bad bet:
#
#   1. the statement must parse as a single SELECT or WITH, with no second
#      statement smuggled in after a semicolon
#   2. no write keyword may appear anywhere in it, comments stripped first so
#      "/**/DELETE" does not slip through
#   3. it runs inside READ ONLY with a statement timeout, so even if 1 and 2 are
#      wrong Postgres itself refuses the write and kills a runaway query
#
# Belt and braces is the right posture here: the first two checks are string
# matching and string matching against SQL is never airtight. The third is the
# one that actually holds -- demonstrated during testing, when "SELECT * INTO
# evil FROM orders" walked straight past the keyword list (INTO was not on it)
# and was stopped by the read-only transaction instead. INTO is on the list now,
# but the lesson is that it should never have needed to be.
_COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)
_WRITES = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|"
    r"vacuum|analyze|reindex|refresh|call|do|set|begin|commit|rollback|"
    r"lock|prepare|execute|listen|notify|into|merge)\b",
    re.I,
)


class UnsafeSQL(Exception):
    pass


def safe_explain_json(sql: str, timeout_ms: int = 15000):
    """EXPLAIN ANALYZE a read-only statement, or refuse to run it at all."""
    bare = _COMMENTS.sub(" ", sql).strip().rstrip(";").strip()
    if not bare:
        raise UnsafeSQL("Nothing to run.")
    if ";" in bare:
        raise UnsafeSQL("One statement at a time — remove the semicolon.")
    if not re.match(r"^\s*(select|with)\b", bare, re.I):
        raise UnsafeSQL("Only SELECT and WITH queries can be explained here.")
    hit = _WRITES.search(bare)
    if hit:
        raise UnsafeSQL(f"'{hit.group(0)}' is not allowed — this page is read-only.")

    conn = _conn()
    with conn.cursor() as cur:
        cur.execute("BEGIN READ ONLY")
        try:
            cur.execute(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
            cur.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + bare)
            plan = cur.fetchone()[0]
        finally:
            cur.execute("ROLLBACK")
    return plan


def sql_panel(sql: str, df: pd.DataFrame | None = None, params: dict | None = None,
              label: str = "SQL behind this"):
    """
    Every number on this site can be traced back to the query that produced it.
    Hiding the SQL is the normal thing for a dashboard to do; showing it is most
    of the point here.
    """
    ms = df.attrs.get("elapsed_ms") if df is not None else None
    caption = f"{label} · {ms:.0f} ms" if ms else label
    with st.expander(caption):
        st.code(sql.strip(), language="sql")
        if params:
            st.caption(f"parameters: `{params}`")
        if st.button("Run EXPLAIN ANALYZE", key=f"ex_{hash(sql) & 0xffffff}"):
            st.code(explain(sql, params), language="text")


def fmt_inr(x) -> str:
    """Indian-format currency, short-scale for readability on tiles."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "-"
    if abs(x) >= 1e7:
        return f"₹{x / 1e7:,.2f} Cr"
    if abs(x) >= 1e5:
        return f"₹{x / 1e5:,.2f} L"
    if abs(x) >= 1e3:
        return f"₹{x / 1e3:,.1f} K"
    return f"₹{x:,.0f}"


def fmt_n(x) -> str:
    try:
        return f"{int(x):,}"
    except (TypeError, ValueError):
        return "-"
