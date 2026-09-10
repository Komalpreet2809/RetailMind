"""
Shared chrome: design tokens, page config, sidebar filters, chart styling.

THE COLOUR DECISION, because it is not obvious and it is easy to get wrong.

The brand accent is an acid lime. It is used everywhere in the interface -- active
states, key figures, the sidebar rule, button hovers -- and it is used *nowhere* as
a data mark. That split is deliberate and it is measured, not felt: lime sits at
OKLCH lightness 0.916 against a 0.43-0.77 band for marks, and contrasts 1.21:1
against a white surface where 3:1 is the floor. A lime bar on a white card is very
close to invisible, and a reader with any contrast loss sees nothing at all.

So the plot area gets a different palette from the interface:

  * one series  -> ink. No identity work is needed when there is only one thing on
                   screen, so the mark takes the same near-black as the type. This
                   is what makes the charts look like the rest of the page.
  * two or more -> SERIES slots below, assigned in fixed order, never cycled. These
                   come from a validated palette and clear CVD separation, the
                   normal-vision floor, chroma and the lightness band.
  * magnitude   -> SEQUENTIAL, a single hue light-to-dark.

Slots 3 and 4 sit below 3:1 on white, which the palette permits only when the
values are also readable another way. Every chart that reaches four series on this
site has its own table underneath, so that relief holds.
"""

import datetime as dt
import streamlit as st

import db
import queries as q

# --------------------------------------------------------------------- interface tokens
INK = "#101112"        # type, dark chrome, single-series marks
INK_2 = "#3D3D3A"      # secondary type
MUTED = "#87867F"      # tertiary type, axis labels
LIME = "#DDF247"       # brand accent -- interface only, never a data mark
LIME_DIM = "#C6DA2E"   # accent hover / pressed
CANVAS = "#F4F4F1"     # page ground
CARD = "#FFFFFF"       # surfaces
LINE = "#E4E4DE"       # hairlines, borders
GRID = "#EDEDE8"       # chart gridlines

# --------------------------------------------------------------------- data tokens
# Fixed order. A fifth series folds into "Other" rather than inventing a hue.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
PALETTE = SERIES       # backwards-compatible alias
SEQUENTIAL = [         # one hue, light -> dark, for magnitude
    [0.00, "#e8f0fc"], [0.20, "#b7d3f6"], [0.40, "#6da7ec"],
    [0.65, "#2a78d6"], [0.85, "#1c5cab"], [1.00, "#0d366b"],
]

FONT = ('-apple-system, "Segoe UI", Inter, Roboto, "Helvetica Neue", '
        "Arial, sans-serif")

CSS = f"""
<style>
  :root {{
    --ink: {INK}; --ink2: {INK_2}; --muted: {MUTED};
    --lime: {LIME}; --canvas: {CANVAS}; --card: {CARD}; --line: {LINE};
  }}

  .stApp {{ background: var(--canvas); }}
  .block-container {{ padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1240px; }}

  html, body, [class*="css"] {{ font-family: {FONT}; }}

  h1 {{ font-size: 2.1rem !important; font-weight: 640 !important;
       letter-spacing: -.028em; color: var(--ink); margin-bottom: .1rem !important; }}
  h2 {{ font-size: 1.18rem !important; font-weight: 620 !important;
       letter-spacing: -.012em; color: var(--ink);
       margin: 2.1rem 0 .5rem !important; }}
  h3 {{ font-size: .98rem !important; font-weight: 600 !important; color: var(--ink); }}

  /* Section headings get a short lime rule instead of a heavier type weight --
     the accent does the separating so the type can stay quiet. */
  h2::before {{
    content: ""; display: block; width: 26px; height: 3px; border-radius: 2px;
    background: var(--lime); margin-bottom: .55rem;
  }}

  .rm-sub {{ color: var(--muted); font-size: .93rem; line-height: 1.55;
            max-width: 68ch; margin: .15rem 0 1.4rem; }}

  /* Metrics as cards. The lime edge marks them as the page's primary readout
     without tinting any of the numbers themselves. */
  [data-testid="stMetric"] {{
    background: var(--card); border: 1px solid var(--line);
    border-radius: 13px; padding: .85rem .95rem .8rem;
    position: relative; overflow: hidden;
  }}
  [data-testid="stMetric"]::before {{
    content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
    background: var(--lime);
  }}
  [data-testid="stMetricValue"] {{
    font-size: 1.42rem !important; font-weight: 620 !important;
    color: var(--ink) !important; letter-spacing: -.02em;
  }}
  [data-testid="stMetricLabel"] {{
    font-size: .7rem !important; font-weight: 560 !important;
    letter-spacing: .07em; text-transform: uppercase; color: var(--muted) !important;
  }}
  [data-testid="stMetricDelta"] {{ font-size: .76rem !important; color: var(--muted) !important; }}

  /* The reading under a chart. Every number on this site is supposed to come
     with one, so it needs to look deliberate rather than like a callout box. */
  .rm-note {{
    background: var(--card); border: 1px solid var(--line);
    border-left: 3px solid var(--lime); border-radius: 0 11px 11px 0;
    padding: .85rem 1.05rem; margin: .9rem 0 1.5rem;
    font-size: .92rem; line-height: 1.62; color: var(--ink2);
  }}
  .rm-note b {{ color: var(--ink); font-weight: 615; }}

  [data-testid="stExpander"] {{
    border: 1px solid var(--line); border-radius: 11px;
    background: var(--card); overflow: hidden;
  }}
  [data-testid="stExpander"] summary {{ font-size: .87rem; color: var(--ink2); }}
  [data-testid="stExpander"] summary:hover {{ color: var(--ink); }}

  [data-testid="stDataFrame"] {{ border: 1px solid var(--line); border-radius: 11px; }}

  [data-testid="stPlotlyChart"] {{
    background: var(--card); border: 1px solid var(--line);
    border-radius: 13px; padding: .9rem 1rem .5rem;
  }}

  .stButton > button {{
    border-radius: 9px; border: 1px solid var(--line); background: var(--card);
    color: var(--ink); font-weight: 560; font-size: .86rem; padding: .34rem .95rem;
    transition: background .12s ease, border-color .12s ease;
  }}
  .stButton > button:hover {{ background: var(--lime); border-color: var(--lime); color: var(--ink); }}
  .stButton > button[kind="primary"] {{ background: var(--ink); border-color: var(--ink); color: #fff; }}
  .stButton > button[kind="primary"]:hover {{ background: var(--lime); border-color: var(--lime); color: var(--ink); }}

  hr, [data-testid="stDivider"] {{ border-color: var(--line) !important; }}

  /* Dark sidebar against the pale canvas, the way the reference puts a dark
     toolbar under light cards. */
  [data-testid="stSidebar"] {{ background: {INK}; border-right: none; }}
  [data-testid="stSidebar"] * {{ color: #EDEDE9; }}
  [data-testid="stSidebar"] h3 {{
    color: #fff !important; font-size: .72rem !important; letter-spacing: .09em;
    text-transform: uppercase; font-weight: 600 !important;
  }}
  [data-testid="stSidebar"] h3::before {{ display: none; }}
  [data-testid="stSidebar"] [data-testid="stCaptionContainer"],
  [data-testid="stSidebar"] .stCaption {{ color: #8E8E88 !important; }}
  [data-testid="stSidebar"] [data-baseweb="select"] > div {{
    background: #1E1F21; border-color: #2C2D30; border-radius: 9px;
  }}
  [data-testid="stSidebarNav"] a {{ border-radius: 8px; }}
  [data-testid="stSidebarNav"] a[aria-current="page"] {{ background: #1E1F21; }}
  [data-testid="stSidebarNav"] a[aria-current="page"] span {{ color: {LIME} !important; font-weight: 600; }}

  code {{ font-size: .84rem; background: #F1F1EC; padding: .08rem .3rem; border-radius: 4px; }}
  [data-testid="stCode"] {{ border-radius: 10px; }}
</style>
"""


def boot():
    """Called once, from the entry point, before any view runs."""
    st.set_page_config(page_title="RetailMind", page_icon="◆",
                       layout="wide", initial_sidebar_state="expanded")
    st.markdown(CSS, unsafe_allow_html=True)


def note(text: str):
    """The 'so what' under a chart. A number without a reading is just a number."""
    st.markdown(f'<div class="rm-note">{text}</div>', unsafe_allow_html=True)


def sub(text: str):
    st.markdown(f'<div class="rm-sub">{text}</div>', unsafe_allow_html=True)


# --------------------------------------------------------------------- charts
def chart(fig, height: int = 360, legend: bool = True, ygrid: bool = True,
          xgrid: bool = False):
    """
    One place that decides how every chart on the site looks.

    Recessive axes and grid, type in ink tokens rather than series colours, a
    unified hover so a reader gets every series at once instead of hunting for
    one mark, and no chart border -- the card around it already draws the edge.
    """
    fig.update_layout(
        height=height,
        margin=dict(l=4, r=8, t=10, b=6),
        paper_bgcolor=CARD,
        plot_bgcolor=CARD,
        font=dict(family=FONT, size=12, color=INK_2),
        hoverlabel=dict(bgcolor=CARD, bordercolor=LINE, font_size=12,
                        font_family=FONT, font_color=INK),
        hovermode="x unified",
        showlegend=legend,
        legend=dict(orientation="h", y=1.14, x=0, xanchor="left",
                    bgcolor="rgba(0,0,0,0)", font=dict(size=11.5, color=INK_2)),
        bargap=.28, bargroupgap=.08,
    )
    fig.update_xaxes(showgrid=xgrid, gridcolor=GRID, zeroline=False, automargin=True,
                     linecolor=LINE, tickfont=dict(size=11, color=MUTED),
                     title_font=dict(size=11.5, color=MUTED), title_standoff=8)
    fig.update_yaxes(showgrid=ygrid, gridcolor=GRID, zeroline=False, automargin=True,
                     linecolor="rgba(0,0,0,0)", tickfont=dict(size=11, color=MUTED),
                     title_font=dict(size=11.5, color=MUTED), title_standoff=8)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


# --------------------------------------------------------------------- filters
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
