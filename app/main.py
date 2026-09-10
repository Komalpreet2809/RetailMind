"""RetailMind :: executive overview (entry page)."""

import plotly.graph_objects as go
import streamlit as st

import db
import queries as q
import ui

ui.page("Overview", "🛍️")
params, brand_label = ui.filters()

st.title("RetailMind")
ui.sub(
    "A retail customer warehouse where the SQL is on show. Every figure below "
    "opens to reveal the query that produced it — and the Query Lab holds the "
    "five queries that were too slow, and what fixed them."
)

# --------------------------------------------------------------------- warehouse strip
stats = db.run(q.WAREHOUSE_STATS).iloc[0]
c = st.columns(5)
c[0].metric("Orders", db.fmt_n(stats["orders"]))
c[1].metric("Customers", db.fmt_n(stats["customers"]))
c[2].metric("Campaign sends", db.fmt_n(stats["sends"]))
c[3].metric("Fact table", stats["orders_size"])
c[4].metric("Database", stats["db_size"])

st.divider()

# --------------------------------------------------------------------- KPIs
st.subheader(f"Business health · {brand_label}")

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

st.divider()

# --------------------------------------------------------------------- trend
st.subheader("Revenue and orders over time")

trend = db.run(q.MONTHLY_TREND, params)
fig = go.Figure()
fig.add_bar(x=trend["month"], y=trend["revenue"], name="Revenue",
            marker_color=ui.PALETTE[0], opacity=.85)
fig.add_scatter(x=trend["month"], y=trend["orders"], name="Orders", yaxis="y2",
                mode="lines+markers", line=dict(color=ui.PALETTE[2], width=2))
fig.update_layout(
    height=380, margin=dict(l=0, r=0, t=10, b=0),
    yaxis=dict(title="Revenue"), yaxis2=dict(title="Orders", overlaying="y", side="right"),
    legend=dict(orientation="h", y=1.12, x=0), hovermode="x unified",
)
st.plotly_chart(fig, width='stretch')

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

st.divider()

# --------------------------------------------------------------------- brand + channel
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
        hide_index=True, width='stretch',
    )
    db.sql_panel(q.REVENUE_BY_BRAND, bybrand,
                 {"start": params["start"], "end": params["end"]}, "SQL · brand split")

with right:
    st.subheader("Channel mix")
    chan = db.run(q.CHANNEL_MIX, params)
    fig = go.Figure(go.Pie(
        labels=chan["channel"], values=chan["revenue"], hole=.55,
        marker=dict(colors=ui.PALETTE[:len(chan)]),
    ))
    fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0),
                      legend=dict(orientation="h", y=-.05))
    st.plotly_chart(fig, width='stretch')
    db.sql_panel(q.CHANNEL_MIX, chan, params, "SQL · channel mix")

st.sidebar.divider()
st.sidebar.caption(
    "Synthetic data, modelled on Indian omnichannel retail: heavy-tailed customer "
    "value, festive seasonality, and campaigns with real holdout groups."
)
