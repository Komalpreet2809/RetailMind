"""
Campaign performance :: which campaigns actually made money.

Response rate is the number everyone reports and it cannot answer the question,
because customers who were going to buy anyway still open the message and still
convert. Every campaign here holds out a random ~15% of its audience, so the
comparison is treated against control and the answer is causal.
"""

import plotly.graph_objects as go
import streamlit as st

import db
import queries as q
import ui

params, brand_label = ui.filters(show_dates=False)

ui.head("Incrementality", "Campaign performance", 
    "Every campaign held out a random slice of its audience. Incremental revenue "
    "is the difference in revenue per customer between treated and held-out, "
    "multiplied by the number treated — the part that would not have happened anyway."
)

perf = db.run(q.CAMPAIGN_PERFORMANCE, {"brand": params["brand"]})
if perf.empty:
    st.warning("No campaigns found.")
    st.stop()

perf["lift_pp"] = perf["treated_conv_pct"] - perf["holdout_conv_pct"]
perf["incr_rev_per_cust"] = perf["treated_rev_per_cust"] - perf["holdout_rev_per_cust"]
perf["incremental_revenue"] = perf["incr_rev_per_cust"] * perf["treated"]
perf["roi"] = (perf["incremental_revenue"] - perf["cost"]) / perf["cost"]

# --------------------------------------------------------------------- by type
st.header("Response rate vs incremental lift, by campaign type")

bytype = perf.groupby("campaign_type").agg(
    campaigns=("campaign_id", "count"),
    open_rate=("open_rate", "mean"),
    treated_conv=("treated_conv_pct", "mean"),
    holdout_conv=("holdout_conv_pct", "mean"),
    incremental=("incremental_revenue", "sum"),
    cost=("cost", "sum"),
).reset_index()
bytype["lift_pp"] = bytype["treated_conv"] - bytype["holdout_conv"]
bytype["roi"] = (bytype["incremental"] - bytype["cost"]) / bytype["cost"]
bytype = bytype.sort_values("lift_pp", ascending=False)

fig = go.Figure()
fig.add_bar(x=bytype["campaign_type"], y=bytype["open_rate"], name="Opened",
            marker_color=ui.SERIES[0], marker_line_width=0,
            hovertemplate="opened %{y:.1f}%<extra></extra>")
fig.add_bar(x=bytype["campaign_type"], y=bytype["treated_conv"], name="Converted (treated)",
            marker_color=ui.SERIES[1], marker_line_width=0,
            hovertemplate="treated %{y:.1f}%<extra></extra>")
fig.add_bar(x=bytype["campaign_type"], y=bytype["holdout_conv"], name="Converted (holdout)",
            marker_color=ui.SERIES[2], marker_line_width=0,
            hovertemplate="holdout %{y:.1f}%<extra></extra>")
fig.update_layout(barmode="group", yaxis_title="% of audience")
ui.chart(fig, height=380)

dud = bytype.loc[bytype["lift_pp"].idxmin()]
hero = bytype.loc[bytype["lift_pp"].idxmax()]
ui.note(
    f"<b>{dud['campaign_type']} campaigns open at {dud['open_rate']:.0f}% and convert "
    f"{dud['treated_conv']:.1f}% — against a holdout of {dud['holdout_conv']:.1f}%.</b> "
    f"That is a lift of {dud['lift_pp']:.1f} percentage points: essentially nothing. "
    f"Those customers were going to buy regardless, and the campaign has been taking "
    f"credit for their orders. Compare {hero['campaign_type']}, which lifts "
    f"{hero['lift_pp']:.1f}pp over its control. Ranked on response rate alone the two "
    f"look comparable — which is exactly how budget ends up in the wrong place."
)

# --------------------------------------------------------------------- roi
st.header("Return on spend, by type")
c = st.columns(len(bytype))
for col, (_, r) in zip(c, bytype.iterrows()):
    col.metric(r["campaign_type"], f"{r['roi']:.1f}×",
               f"{db.fmt_inr(r['incremental'])} incremental", delta_color="off")

# --------------------------------------------------------------------- detail
st.header("Every campaign")

show = perf.sort_values("incremental_revenue", ascending=False)[[
    "campaign_name", "campaign_type", "channel", "treated", "holdout",
    "open_rate", "treated_conv_pct", "holdout_conv_pct", "lift_pp",
    "cost", "incremental_revenue", "roi",
]].copy()
for c_ in ("open_rate", "treated_conv_pct", "holdout_conv_pct", "lift_pp"):
    show[c_] = show[c_].map(lambda v: f"{v:.1f}%")
show["cost"] = show["cost"].map(db.fmt_inr)
show["incremental_revenue"] = show["incremental_revenue"].map(db.fmt_inr)
show["roi"] = show["roi"].map(lambda v: f"{v:.1f}×")
show["treated"] = show["treated"].map(db.fmt_n)
show["holdout"] = show["holdout"].map(db.fmt_n)

st.dataframe(
    show.rename(columns={
        "campaign_name": "Campaign", "campaign_type": "Type", "channel": "Channel",
        "treated": "Treated", "holdout": "Holdout", "open_rate": "Open",
        "treated_conv_pct": "Conv (treated)", "holdout_conv_pct": "Conv (holdout)",
        "lift_pp": "Lift", "cost": "Cost",
        "incremental_revenue": "Incremental revenue", "roi": "ROI",
    }),
    hide_index=True, width='stretch', height=430,
)

db.sql_panel(q.CAMPAIGN_PERFORMANCE, perf, {"brand": params["brand"]}, "SQL · campaign performance with holdout")

st.header("The recommendation")
st.markdown(
    f"Stop running **{dud['campaign_type']}** in its current form. It is not "
    f"underperforming — it is not doing anything, and the "
    f"{db.fmt_inr(dud['cost'])} behind it is buying orders that were already "
    f"coming. Move that budget to **{hero['campaign_type']}**, which clears its "
    f"control by {hero['lift_pp']:.1f}pp, and keep the holdout in place so the "
    f"next read is just as honest."
)

ui.footer()
