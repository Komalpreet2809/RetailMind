"""RetailMind :: executive overview (entry page)."""

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import db
import queries as q
import ui

params, brand_label = ui.filters()

stats = db.run(q.WAREHOUSE_STATS).iloc[0]

ui.hero(
    "RetailMind",
    "A retail customer warehouse where the SQL is on show. Every figure below "
    "opens to reveal the query behind it — the Query Lab holds the five queries "
    "that were too slow and what fixed them, and the Plan Doctor will read the "
    "plan of anything you write yourself.",
    chips=[
        ("Orders", db.fmt_n(stats["orders"])),
        ("Customers", db.fmt_n(stats["customers"])),
        ("Campaign sends", db.fmt_n(stats["sends"])),
        ("Fact table", stats["orders_size"]),
        ("Postgres", "17 · Neon"),
    ],
)

# --------------------------------------------------------------------- KPIs
st.header(f"Business health · {brand_label}")

kpi = db.run(q.KPIS, params).iloc[0]
rep = db.run(q.REPEAT_RATE, params).iloc[0]

c = st.columns(6)
c[0].metric("Revenue", db.fmt_inr(kpi["revenue"]))
c[1].metric("Orders", db.fmt_n(kpi["orders"]))
c[2].metric("Customers", db.fmt_n(kpi["active_customers"]))
c[3].metric("Avg order value", db.fmt_inr(kpi["aov"]))
c[4].metric("Revenue / customer", db.fmt_inr(kpi["revenue_per_customer"]))
c[5].metric("Repeat rate", f"{rep['repeat_rate_pct']:.1f}%")

single_pct = 100.0 - float(rep["repeat_rate_pct"])
ui.note(
    f"<b>{single_pct:.1f}% of customers bought exactly once</b> "
    f"({db.fmt_n(rep['single_visit'])} people). Moving even a tenth of them to a "
    f"second purchase is worth more than acquiring the same number of new "
    f"customers, because the acquisition cost is already sunk."
)

db.sql_panel(q.KPIS, None, params, "SQL · headline metrics")
db.sql_panel(q.REPEAT_RATE, None, params, "SQL · repeat vs single-visit")

# --------------------------------------------------------------------- trend
st.header("Revenue and orders over time")
ui.sub(
    "Two panels rather than two y-axes. Revenue and order count share an x-axis "
    "and nothing else — drawn on a shared scale, the reader's eye invents "
    "crossings and gaps that are artefacts of where the axes were pinned."
)

trend = db.run(q.MONTHLY_TREND, params)

fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=.07,
                    row_heights=[.62, .38])
fig.add_bar(x=trend["month"], y=trend["revenue"], name="Revenue",
            marker_color=ui.INK, marker_line_width=0, row=1, col=1,
            hovertemplate="₹%{y:,.0f}<extra></extra>")
fig.add_scatter(x=trend["month"], y=trend["orders"], name="Orders", mode="lines",
                line=dict(color=ui.INK, width=2), row=2, col=1,
                hovertemplate="%{y:,.0f} orders<extra></extra>")
fig.update_yaxes(title_text="Revenue", row=1, col=1)
fig.update_yaxes(title_text="Orders", row=2, col=1)
ui.chart(fig, height=420, legend=False)

if len(trend) >= 12:
    peak = trend.loc[trend["revenue"].idxmax()]
    typical = trend["revenue"].median()
    ui.note(
        f"Revenue peaks in <b>{peak['month']:%B %Y}</b> at {db.fmt_inr(peak['revenue'])}, "
        f"about {peak['revenue'] / typical:.1f}× a typical month. The festive quarter "
        f"is when acquisition is cheapest — and it is also the cohort most likely to "
        f"lapse, which the retention page bears out."
    )

db.sql_panel(q.MONTHLY_TREND, trend, params, "SQL · monthly trend")

# --------------------------------------------------------------------- brand + channel
st.header("Where the revenue comes from")

left, right = st.columns([3, 2])

with left:
    st.subheader("By brand")
    bybrand = db.run(q.REVENUE_BY_BRAND, {"start": params["start"], "end": params["end"]})
    show = bybrand.copy()
    show["revenue"] = show["revenue"].map(db.fmt_inr)
    show["aov"] = show["aov"].map(db.fmt_inr)
    show["orders"] = show["orders"].map(db.fmt_n)
    show["customers"] = show["customers"].map(db.fmt_n)
    st.dataframe(
        show.rename(columns={"brand_name": "Brand", "category": "Category",
                             "orders": "Orders", "revenue": "Revenue",
                             "customers": "Customers", "aov": "AOV"}),
        hide_index=True, width="stretch",
    )
    db.sql_panel(q.REVENUE_BY_BRAND, bybrand,
                 {"start": params["start"], "end": params["end"]}, "SQL · brand split")

with right:
    st.subheader("Channel mix")
    chan = db.run(q.CHANNEL_MIX, params).sort_values("revenue")
    total = chan["revenue"].sum()
    # A ranked bar rather than a donut: three shares are read by comparing
    # lengths against a common baseline, which is the one comparison people do
    # accurately. Angles are not.
    fig = go.Figure(go.Bar(
        x=chan["revenue"], y=chan["channel"], orientation="h",
        marker_color=ui.INK, marker_line_width=0,
        text=[f"{100 * v / total:.0f}%" for v in chan["revenue"]],
        textposition="outside", textfont=dict(size=12, color=ui.INK_2),
        hovertemplate="%{y}: ₹%{x:,.0f}<extra></extra>",
    ))
    fig.update_xaxes(visible=False, range=[0, chan["revenue"].max() * 1.18])
    ui.chart(fig, height=230, legend=False, ygrid=False)
    db.sql_panel(q.CHANNEL_MIX, chan, params, "SQL · channel mix")

ui.footer()
