"""Connection handling and the query helpers every page uses."""

import os
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


def explain(sql: str, params: dict | None = None) -> str:
    conn = _conn()
    with conn.cursor() as cur:
        cur.execute("EXPLAIN (ANALYZE, BUFFERS) " + sql, params)
        return "\n".join(r[0] for r in cur.fetchall())


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
