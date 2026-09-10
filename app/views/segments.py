"""RFM segmentation :: who is actually worth talking to."""

import plotly.graph_objects as go
import streamlit as st

import db
import queries as q
import ui

params, brand_label = ui.filters(show_dates=False)

ui.head("RFM segmentation", "Customer segments", 
    "Recency, frequency and monetary value, each scored into quintiles across the "
    "customer base, then combined into segments. Scoring by quintile rather than "
    "by fixed thresholds means the split still works when it is pointed at one "
    "brand instead of all five."
)

rfm = db.run(q.RFM, {"brand": params["brand"]})
if rfm.empty:
    st.warning("No customers match this filter.")
    st.stop()

rfm["customer_share"] = 100 * rfm["customers"] / rfm["customers"].sum()
rfm["revenue_share"] = 100 * rfm["total_revenue"] / rfm["total_revenue"].sum()

ORDER = ["Champions", "Loyal", "Needs Attention", "New / Promising", "At Risk", "Lost"]
rfm["_o"] = rfm["segment"].map({s: i for i, s in enumerate(ORDER)}).fillna(9)
rfm = rfm.sort_values("_o")

# --------------------------------------------------------------------- share chart
st.header(f"Share of customers vs share of revenue · {brand_label}")

fig = go.Figure()
fig.add_bar(x=rfm["segment"], y=rfm["customer_share"], name="% of customers",
            marker_color=ui.SERIES[0], marker_line_width=0,
            hovertemplate="%{y:.1f}% of customers<extra></extra>")
fig.add_bar(x=rfm["segment"], y=rfm["revenue_share"], name="% of revenue",
            marker_color=ui.SERIES[1], marker_line_width=0,
            hovertemplate="%{y:.1f}% of revenue<extra></extra>")
fig.update_layout(barmode="group", yaxis_title="% of total")
ui.chart(fig, height=380)

champ = rfm[rfm["segment"] == "Champions"]
risk = rfm[rfm["segment"] == "At Risk"]
if not champ.empty and not risk.empty:
    ch, rk = champ.iloc[0], risk.iloc[0]
    ui.note(
        f"<b>Champions are {ch['customer_share']:.1f}% of customers and "
        f"{ch['revenue_share']:.1f}% of revenue.</b> At Risk is "
        f"{rk['customer_share']:.1f}% of customers carrying {rk['revenue_share']:.1f}% "
        f"of revenue — people who used to buy often and have now gone quiet for "
        f"{int(rk['avg_recency_days'])} days on average. That group is where a "
        f"retention budget earns the most, because the spend is proven and the "
        f"relationship is only lapsing, not gone."
    )

# --------------------------------------------------------------------- table
st.header("Segment detail")

show = rfm[["segment", "customers", "customer_share", "avg_orders",
            "avg_recency_days", "avg_spend", "total_revenue", "revenue_share"]].copy()
show["customers"] = show["customers"].map(db.fmt_n)
show["customer_share"] = show["customer_share"].map(lambda v: f"{v:.1f}%")
show["revenue_share"] = show["revenue_share"].map(lambda v: f"{v:.1f}%")
show["avg_spend"] = show["avg_spend"].map(db.fmt_inr)
show["total_revenue"] = show["total_revenue"].map(db.fmt_inr)
show["avg_recency_days"] = show["avg_recency_days"].map(lambda v: f"{int(v)}d")

st.dataframe(
    show.rename(columns={
        "segment": "Segment", "customers": "Customers", "customer_share": "% of base",
        "avg_orders": "Avg orders", "avg_recency_days": "Avg recency",
        "avg_spend": "Avg spend", "total_revenue": "Revenue", "revenue_share": "% of revenue",
    }),
    hide_index=True, width='stretch',
)

db.sql_panel(q.RFM, rfm, {"brand": params["brand"]}, "SQL · RFM segmentation")

# --------------------------------------------------------------------- reading
st.header("What to do with this")
a, b, c = st.columns(3)
a.markdown(
    "**Champions** — do not discount to them. They already buy at full price; a "
    "coupon here is margin handed away. Early access and tier perks instead."
)
b.markdown(
    "**At Risk** — the only segment where an aggressive win-back offer pays for "
    "itself, because the alternative is losing proven spend. Worth a control group."
)
c.markdown(
    "**Lost** — cheap channels only. Reacquiring these customers generally costs "
    "more than acquiring a new one, and the campaign page shows exactly that."
)
