"""Shared chrome: page config, sidebar filters, and the small styling layer."""

import datetime as dt
import streamlit as st

import db
import queries as q

PALETTE = ["#2563eb", "#0d9488", "#f59e0b", "#dc2626", "#7c3aed", "#0891b2"]

CSS = """
<style>
  .block-container { padding-top: 2.4rem; max-width: 1220px; }
  [data-testid="stMetricValue"] { font-size: 1.55rem; }
  [data-testid="stMetricLabel"] { font-size: .78rem; letter-spacing: .04em;
      text-transform: uppercase; opacity: .7; }
  .rm-note { border-left: 3px solid #2563eb; padding: .55rem .9rem; margin: .5rem 0 1.1rem;
      background: rgba(37,99,235,.06); border-radius: 0 6px 6px 0; font-size: .92rem; }
  .rm-sub { opacity: .65; font-size: .9rem; margin-top: -.6rem; }
  code { font-size: .85rem; }
</style>
"""


def page(title: str, icon: str = "📊"):
    st.set_page_config(page_title=f"{title} · RetailMind", page_icon=icon,
                       layout="wide", initial_sidebar_state="expanded")
    st.markdown(CSS, unsafe_allow_html=True)


def note(text: str):
    """The 'so what' under a chart. A number without a reading is just a number."""
    st.markdown(f'<div class="rm-note">{text}</div>', unsafe_allow_html=True)


def sub(text: str):
    st.markdown(f'<div class="rm-sub">{text}</div>', unsafe_allow_html=True)


@st.cache_data(ttl=3600, show_spinner=False)
def _brands():
    return db.run(q.BRANDS)


@st.cache_data(ttl=3600, show_spinner=False)
def _range():
    r = db.run(q.DATE_RANGE)
    return r.iloc[0]["lo"], r.iloc[0]["hi"]


def filters(show_dates: bool = True):
    """Brand + date-range picker. Returns the params dict every query expects."""
    brands = _brands()
    lo, hi = _range()

    st.sidebar.markdown("### Filters")
    names = ["All brands"] + brands["brand_name"].tolist()
    pick = st.sidebar.selectbox("Brand", names, index=0)
    brand = None if pick == "All brands" else int(
        brands.loc[brands["brand_name"] == pick, "brand_id"].iloc[0]
    )

    start, end = lo, hi
    if show_dates:
        preset = st.sidebar.selectbox(
            "Period", ["Full history", "Last 12 months", "Last 6 months", "Last 90 days", "Custom"]
        )
        spans = {"Last 12 months": 365, "Last 6 months": 182, "Last 90 days": 90}
        if preset in spans:
            start = hi - dt.timedelta(days=spans[preset])
        elif preset == "Custom":
            picked = st.sidebar.date_input("Range", (lo, hi), min_value=lo, max_value=hi)
            if isinstance(picked, tuple) and len(picked) == 2:
                start, end = picked

    st.sidebar.caption(f"Warehouse covers {lo} → {hi}")
    return {"brand": brand, "start": start, "end": end}, pick
