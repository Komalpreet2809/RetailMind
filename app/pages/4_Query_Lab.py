"""
Query Lab :: the five queries that were too slow, and what fixed them.

Nothing here is illustrative. Each pair was run against the real 9.4M-row
warehouse with the fix genuinely absent, then genuinely present, and the plans
below are what Postgres actually chose in each state.
"""

import json
import os
import plotly.graph_objects as go
import streamlit as st

import db
import ui

ui.page("Query Lab", "⚡")

BENCH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "benchmarks.json")


@st.cache_data(ttl=3600, show_spinner=False)
def load():
    with open(BENCH) as f:
        return json.load(f)


data = load()
res = data["results"]

st.title("Query Lab")
ui.sub(
    "Five queries that ran fine while I was building against a few thousand rows "
    "and fell over at nine million. Each one below shows the plan Postgres chose "
    "before the fix, the diagnosis, and the plan after."
)

st.markdown(
    f"<div class='rm-note'>Measured against <b>{data['order_count']:,} orders</b> "
    f"({data['repeats']} runs, median reported, warm cache on both sides). "
    f"Cold-cache numbers would look far more impressive and would mean much less — "
    f"the comparison here is like for like.</div>",
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------- summary
st.subheader("The five")

fig = go.Figure()
labels = [r["title"] for r in res]
fig.add_bar(y=labels, x=[r["slow_ms"] for r in res], name="Before",
            orientation="h", marker_color=ui.PALETTE[3], opacity=.85)
fig.add_bar(y=labels, x=[r["fast_ms"] for r in res], name="After",
            orientation="h", marker_color=ui.PALETTE[1], opacity=.9)
fig.update_layout(
    height=330, margin=dict(l=0, r=0, t=8, b=0), barmode="group",
    xaxis=dict(title="milliseconds (log scale)", type="log"),
    legend=dict(orientation="h", y=1.15, x=0),
    yaxis=dict(autorange="reversed"),
)
st.plotly_chart(fig, width='stretch')

cols = st.columns(len(res))
for col, r in zip(cols, res):
    col.metric(r["title"].split(" for ")[0][:22], f"{r['speedup']:.0f}×",
               f"{r['slow_ms']:.0f} → {r['fast_ms']:.0f} ms", delta_color="off")

worst = max(res, key=lambda r: r["slow_ms"])
best = max(res, key=lambda r: r["speedup"])
ui.note(
    f"The worst offender was <b>{worst['title'].lower()}</b> at "
    f"{worst['slow_ms']:.0f} ms; the largest win was <b>{best['speedup']:.0f}×</b> on "
    f"{best['title'].lower()}. Four of the five needed either an index that was "
    f"missing or a rewrite that let an existing index be used — which is usually "
    f"where the time is."
)

st.divider()

# --------------------------------------------------------------------- detail
for i, r in enumerate(res, 1):
    st.subheader(f"{i}. {r['title']}")
    st.caption(f"**{r['question']}** — {r['lesson']}")

    m = st.columns(3)
    m[0].metric("Before", f"{r['slow_ms']:,.0f} ms")
    m[1].metric("After", f"{r['fast_ms']:,.0f} ms")
    m[2].metric("Speed-up", f"{r['speedup']:.0f}×")

    st.markdown(f"<div class='rm-note'>{r['diagnosis']}</div>", unsafe_allow_html=True)

    if r["fix_sql"] and r["fix_sql"] != "(query rewrite only)":
        st.markdown("**The fix**")
        st.code(r["fix_sql"], language="sql")

    a, b = st.columns(2)
    with a:
        st.markdown(f"**Before · {r['slow_ms']:,.0f} ms**")
        st.code(r["slow_sql"], language="sql")
    with b:
        st.markdown(f"**After · {r['fast_ms']:,.0f} ms**")
        st.code(r["fast_sql"], language="sql")

    with st.expander("Execution plans (EXPLAIN ANALYZE, BUFFERS)"):
        pa, pb = st.columns(2)
        with pa:
            st.caption("before")
            st.code(r["slow_plan"], language="text")
        with pb:
            st.caption("after")
            st.code(r["fast_plan"], language="text")

    with st.expander("Run both against the live database now"):
        st.caption(
            "Re-runs both queries against the warehouse this instant. Timings will "
            "differ from the recorded medians above — shared hosting, cache state, "
            "and whoever else is on the page all move the number."
        )
        if st.button("Run", key=f"run_{r['id']}"):
            try:
                s = db.run(r["slow_sql"])
                f = db.run(r["fast_sql"])
                sm = s.attrs.get("elapsed_ms", 0)
                fm = f.attrs.get("elapsed_ms", 0)
                c1, c2, c3 = st.columns(3)
                c1.metric("Before (live)", f"{sm:,.0f} ms")
                c2.metric("After (live)", f"{fm:,.0f} ms")
                c3.metric("Speed-up", f"{sm / max(fm, 1e-9):.0f}×")
                st.dataframe(f.head(8), hide_index=True, width='stretch')
            except Exception as e:  # noqa: BLE001 - surfaced to the reader on purpose
                st.error(f"Live run failed: {e}")

    st.divider()

st.caption(f"Benchmarks generated {data['generated_at']} · `scripts/benchmark.py`")
