"""
Query Lab :: the five queries that were too slow, and what fixed them.

Nothing here is illustrative. Each pair was run with the fix genuinely absent,
then genuinely present, and the plans shown are what Postgres actually chose in
each state.

Two sets of numbers, deliberately:

  * the hosted database, which is what the Run buttons below actually talk to
  * a local build with roughly three times the rows

They are shown side by side because publishing only the flattering one would be
dishonest, but they are NOT a scaling curve and the page says so. The hosted
database has fewer rows and is still slower in absolute terms: free-tier compute
on network-attached storage behaves nothing like a local NVMe disk. Two variables
move between those columns, so neither can be credited with the difference.

What does survive the change of machine is the part worth having: the same query
shapes are slow in both places, the same fixes work in both places, and the
ratios hold. scripts/scaling.py is the honest scaling experiment -- one machine,
four row counts.
"""

import json
import os
import plotly.graph_objects as go
import streamlit as st

import db
import ui


DATA = os.path.join(os.path.dirname(__file__), "..", "..", "data")


@st.cache_data(ttl=3600, show_spinner=False)
def load(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


hosted = load("benchmarks.json")
full = load("benchmarks_local.json")

if hosted is None:
    st.error("No benchmark results found. Run `python scripts/benchmark.py`.")
    st.stop()

res = hosted["results"]
full_by_id = {r["id"]: r for r in (full or {}).get("results", [])}
# Only treat the second set as a different scale if it genuinely is one.
comparable = full and full.get("order_count", 0) > hosted["order_count"] * 1.5

ui.head("Query performance", "Query Lab", 
    "Five queries that ran fine while I was building against a few thousand rows "
    "and fell over further up. Each shows the plan Postgres chose before the fix, "
    "the diagnosis, and the plan after."
)

if comparable:
    st.markdown(
        f"<div class='rm-note'>Two environments below. <b>Hosted</b> is this live "
        f"database — {hosted['order_count']:,} orders on a free 0.5 GB tier, and what "
        f"the Run buttons talk to. <b>Local</b> is {full['order_count']:,} orders on a "
        f"laptop. Every figure is the median of {hosted['repeats']} runs of the server's "
        f"own reported execution time, warm cache on both sides — measuring from the "
        f"client would add ~200ms of network round trip to every hosted query and bury "
        f"the result in latency.</div>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f"<div class='rm-note'>Measured against <b>{hosted['order_count']:,} orders</b> "
        f"({hosted['repeats']} runs, median reported, warm cache on both sides).</div>",
        unsafe_allow_html=True,
    )

# --------------------------------------------------------------------- summary
st.header("The five")

fig = go.Figure()
labels = [r["title"] for r in res]
fig.add_bar(y=labels, x=[r["slow_ms"] for r in res], name="Before the fix",
            orientation="h", marker_color=ui.SERIES[1], marker_line_width=0,
            hovertemplate="before: %{x:,.0f} ms<extra></extra>")
fig.add_bar(y=labels, x=[r["fast_ms"] for r in res], name="After the fix",
            orientation="h", marker_color=ui.SERIES[0], marker_line_width=0,
            hovertemplate="after: %{x:,.0f} ms<extra></extra>")
fig.update_layout(
    barmode="group",
    xaxis=dict(title="milliseconds (log scale)", type="log"),
    yaxis=dict(autorange="reversed"),
)
ui.chart(fig, height=340, xgrid=True, ygrid=False)

if comparable:
    st.markdown("**The same five, on two different machines**")
    rows = []
    for r in res:
        f = full_by_id.get(r["id"])
        rows.append({
            "Query": r["title"],
            f"Hosted · {hosted['order_count'] / 1e6:.1f}M rows":
                f"{r['slow_ms']:,.0f} → {r['fast_ms']:,.0f} ms  ({r['speedup']:.0f}×)",
            f"Local · {full['order_count'] / 1e6:.1f}M rows":
                f"{f['slow_ms']:,.0f} → {f['fast_ms']:,.0f} ms  ({f['speedup']:.0f}×)" if f else "—",
        })
    st.dataframe(rows, hide_index=True, width="stretch")
    ui.note(
        "Read these as two independent results, <b>not</b> as a scaling curve. The "
        "hosted database holds a third of the rows and is still slower in absolute "
        "terms, because free-tier compute with network-attached storage is a very "
        "different machine from a local NVMe disk with 512MB of shared buffers. Row "
        "count and hardware both change between the columns, so the difference "
        "between them cannot be attributed to either one. What does carry across is "
        "the finding: the same query shapes are slow on both, the same fixes work on "
        "both, and the ratios hold. For a genuine scaling curve — identical hardware, "
        "varying row counts — see <code>scripts/scaling.py</code>."
    )

cols = st.columns(len(res))
for col, r in zip(cols, res):
    col.metric(r["title"].split(" for ")[0][:22], f"{r['speedup']:.0f}×",
               f"{r['slow_ms']:.0f} → {r['fast_ms']:.0f} ms", delta_color="off")

st.divider()

# --------------------------------------------------------------------- scaling
scaling = load("scaling.json")
if scaling and len(scaling.get("points", [])) > 2:
    pts = scaling["points"]
    sizes = [p["orders"] for p in pts]
    grew = sizes[-1] / sizes[0]

    st.header("What actually happens as the table grows")
    ui.sub(
        "One machine, one build, four warehouse sizes. Unlike the two columns "
        "above, only one thing changes here — the number of rows — so the shape of "
        "each line means something."
    )

    fig = go.Figure()
    for i, (qid, lab) in enumerate(scaling["labels"].items()):
        c = ui.SERIES[i % len(ui.SERIES)]
        ys = [p["results"][qid]["slow_ms"] for p in pts if qid in p["results"]]
        yf = [p["results"][qid]["fast_ms"] for p in pts if qid in p["results"]]
        fig.add_scatter(x=sizes, y=ys, name=lab["title"], mode="lines+markers",
                        line=dict(color=c, width=2.5))
        fig.add_scatter(x=sizes, y=yf, name=f"{lab['title']} (fixed)", mode="lines",
                        line=dict(color=c, width=1.5, dash="dot"), showlegend=False,
                        hovertemplate="fixed: %{y:.0f} ms<extra></extra>")
    fig.update_layout(
        xaxis=dict(title="orders in the warehouse", type="log"),
        yaxis=dict(title="execution time (ms, log scale)", type="log"),
    )
    ui.chart(fig, height=440, xgrid=True)
    st.caption("Solid = before the fix. Dotted = the same query after it.")

    rows = []
    for qid, lab in scaling["labels"].items():
        first = pts[0]["results"].get(qid)
        last = pts[-1]["results"].get(qid)
        if not (first and last):
            continue
        rows.append({
            "Query": lab["title"],
            f"{sizes[0] / 1e3:.0f}k rows": f"{first['slow_ms']:,.0f} ms",
            f"{sizes[-1] / 1e6:.1f}M rows": f"{last['slow_ms']:,.0f} ms",
            "Growth": f"{last['slow_ms'] / max(first['slow_ms'], 1e-9):.0f}×",
            "After the fix": f"{first['fast_ms']:,.0f} → {last['fast_ms']:,.0f} ms",
        })
    st.dataframe(rows, hide_index=True, width="stretch")

    ui.note(
        f"The data grew <b>{grew:.0f}×</b> across these four builds. Three of the four "
        f"queries grew roughly 30–40× with it — and the important part is where they "
        f"started: 3ms, 9ms, 12ms. Nobody notices a 3ms query. Those are the ones "
        f"that pass review, ship, and then take a dashboard down eighteen months "
        f"later when the table has caught up with them.<br><br>"
        f"The correlated subquery is the exception and worth understanding separately. "
        f"It grew only 4× — because it was <b>already slow at 99,000 rows</b>. Its cost "
        f"is set by how many times the subquery runs, which barely changes with table "
        f"size, so it is the one bad query you would actually catch in development. "
        f"The others hide until production.<br><br>"
        f"Every dotted line is close to flat. That is the whole objective: after the "
        f"fix, cost tracks the rows returned rather than the rows stored."
    )

    st.caption(f"`scripts/scaling.py` · generated {scaling['generated_at']}")
    st.divider()

# --------------------------------------------------------------------- detail
has_part = db.table_exists("orders_part")

for i, r in enumerate(res, 1):
    st.subheader(f"{i}. {r['title']}")
    st.caption(f"**{r['question']}** — {r['lesson']}")

    f = full_by_id.get(r["id"])
    m = st.columns(4 if f else 3)
    m[0].metric("Before", f"{r['slow_ms']:,.0f} ms")
    m[1].metric("After", f"{r['fast_ms']:,.0f} ms")
    m[2].metric("Speed-up", f"{r['speedup']:.0f}×")
    if f:
        m[3].metric(f"Before at {full['order_count'] / 1e6:.1f}M",
                    f"{f['slow_ms']:,.0f} ms", f"{f['speedup']:.0f}× when fixed",
                    delta_color="off")

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

    needs_part = "orders_part" in (r["fast_sql"] + r["slow_sql"])
    if needs_part and not has_part:
        st.caption(
            "The partitioned copy of the fact table is not present on the hosted "
            "database — it would double storage on a 0.5 GB tier for one "
            "demonstration. The plans and timings above are from the full local "
            "build, where it exists."
        )
    else:
        with st.expander("Run both against the live database now"):
            st.caption(
                "Re-runs both queries against the hosted warehouse this instant. "
                "Timings will differ from the recorded medians — shared compute, "
                "cache state, and a database that suspends when idle all move the "
                "number. The first run after a quiet spell is always the slowest."
            )
            if st.button("Run", key=f"run_{r['id']}"):
                try:
                    s = db.run(r["slow_sql"])
                    fst = db.run(r["fast_sql"])
                    sm = s.attrs.get("elapsed_ms", 0)
                    fm = fst.attrs.get("elapsed_ms", 0)
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Before (live)", f"{sm:,.0f} ms")
                    c2.metric("After (live)", f"{fm:,.0f} ms")
                    c3.metric("Speed-up", f"{sm / max(fm, 1e-9):.0f}×")
                    st.dataframe(fst.head(8), hide_index=True, width="stretch")
                except Exception as e:  # noqa: BLE001 - surfaced to the reader on purpose
                    st.error(f"Live run failed: {e}")

    st.divider()

# --------------------------------------------------------------------- rollups
st.header("The one an index could not fix")
st.markdown(
    "Every fix above is an index or a rewrite. The dashboard's own queries were a "
    "different problem: revenue by month, revenue by brand and the cohort grid each "
    "aggregate **every row in the table**, and an index cannot help a query that "
    "genuinely needs all of them. At full scale those three cost 6.2s, 8.6s and 7.6s."
)
st.markdown(
    "The answer there was to stop recomputing history that cannot change — "
    "materialized rollups, refreshed on a schedule rather than on every page load. "
    "**Five pages went from ~26s of query time to 401ms.** The trade is that the "
    "dashboard is now eventually consistent, which for three years of closed trading "
    "history costs nothing, and for a real-time operational view would be the wrong "
    "call entirely."
)
st.code("sql/05_rollups.sql", language="text")

st.caption(
    f"Hosted benchmarks generated {hosted['generated_at']}"
    + (f" · full-scale build {full['generated_at']}" if comparable else "")
    + " · `scripts/benchmark.py`"
)

ui.footer()
