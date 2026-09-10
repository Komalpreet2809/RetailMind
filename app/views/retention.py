"""Cohort retention :: does anyone come back, and does it depend on when they arrived."""

import numpy as np
import plotly.graph_objects as go
import streamlit as st

import db
import queries as q
import ui

params, brand_label = ui.filters(show_dates=False)

ui.head("Cohort analysis", "Cohort retention", 
    "Customers grouped by the month of their first order, then tracked forward. "
    "Row = acquisition month, column = months since. Every cell is the share of "
    "that cohort who ordered again in that month."
)

raw = db.run(q.COHORTS, {"brand": params["brand"]})
if raw.empty:
    st.warning("No orders match this filter.")
    st.stop()

pivot = raw.pivot(index="cohort_month", columns="month_n", values="customers").sort_index()
base = pivot[0]
pct = pivot.div(base, axis=0) * 100

# Cohorts near the end of the window have not had time to mature; showing them
# next to three-year-old cohorts invites a false read.
pct = pct.iloc[:-2] if len(pct) > 4 else pct

st.header(f"Retention by acquisition cohort · {brand_label}")

z = pct.values
text = np.where(np.isnan(z), "", np.round(z, 0).astype("O")).astype(str)
text = np.char.replace(text, ".0", "")
text = np.where(text == "", "", np.char.add(text, "%"))

fig = go.Figure(go.Heatmap(
    z=z,
    x=[f"M{c}" for c in pct.columns],
    y=[d.strftime("%b %Y") for d in pct.index],
    text=text, texttemplate="%{text}",
    colorscale=ui.SEQUENTIAL,
    zmin=0, zmax=float(np.nanmax(z[:, 1:])) if z.shape[1] > 1 else 100,
    hovertemplate="%{y} · %{x}<br>%{z:.1f}% retained<extra></extra>",
    colorbar=dict(title="%", thickness=11, outlinewidth=0,
                  tickfont=dict(size=10, color=ui.MUTED)),
))
fig.update_layout(xaxis=dict(side="top"), yaxis=dict(autorange="reversed"))
ui.chart(fig, height=max(430, 27 * len(pct)), legend=False, ygrid=False)

# --------------------------------------------------------------------- reading
if pct.shape[1] > 3:
    m1 = pct[1].mean()
    m3 = pct[3].mean()
    m6 = pct[6].mean() if 6 in pct.columns else np.nan
    best_i = pct[3].idxmax()
    worst_i = pct[3].idxmin()

    c = st.columns(4)
    c[0].metric("Month 1 (avg)", f"{m1:.0f}%")
    c[1].metric("Month 3 (avg)", f"{m3:.0f}%")
    if not np.isnan(m6):
        c[2].metric("Month 6 (avg)", f"{m6:.0f}%")
    c[3].metric("Best cohort (M3)", best_i.strftime("%b %Y"), f"{pct.loc[best_i, 3]:.0f}%",
                delta_color="off")

    ui.note(
        f"Retention falls from {m1:.0f}% at month one to {m3:.0f}% by month three — "
        f"<b>the first eight weeks decide almost everything</b>. The gap between the "
        f"best cohort ({best_i:%b %Y}, {pct.loc[best_i, 3]:.0f}% at M3) and the worst "
        f"({worst_i:%b %Y}, {pct.loc[worst_i, 3]:.0f}%) is the interesting part: "
        f"cohorts acquired during festive discounting come in large and leave fast, "
        f"because the offer acquired them, not the brand. Judging a festive campaign "
        f"on signups alone will flatter it every time."
    )

db.sql_panel(q.COHORTS, raw, {"brand": params["brand"]}, "SQL · cohort retention")

st.header("Cohort sizes")
st.caption("Retention percentages are meaningless without the denominator.")
sizes = base.to_frame("customers")
sizes.index = [d.strftime("%b %Y") for d in sizes.index]
st.bar_chart(sizes, height=220, color=ui.INK)
