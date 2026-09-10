"""
Shared chrome: design tokens, app shell, sidebar filters, chart styling.

THE COLOUR DECISION, because it is easy to get backwards.

The brand accent is an acid lime. Where it is allowed to go is decided by
contrast, not by taste:

  * as a BACKGROUND with ink text on top -- hero panel, active nav, chips, badges
    -- it measures roughly 16:1 against near-black. That is the most legible
    pairing on the whole site, so this is where the brand gets to be loud.
  * as a MARK on white -- a bar, a line, a dot -- it is 1.21:1 and sits at OKLCH
    lightness 0.916 against a 0.43-0.77 band for marks. Effectively invisible,
    and gone entirely for a reader with any contrast loss. So it never goes there.

Loud and legible are not in tension; they just require putting the accent behind
the text rather than into the data.

The plot area therefore runs its own palette:

  * one series  -> ink, the same near-black as the type
  * two or more -> SERIES below, fixed order, never cycled, from a validated
                   palette clearing CVD separation, the normal-vision floor,
                   chroma, and the lightness band
  * magnitude   -> SEQUENTIAL, one hue light-to-dark

Slots 3 and 4 fall below 3:1 on white, which the palette permits only where the
values are legible another way. Every chart here that reaches four series has a
table beneath it, so that relief holds.
"""

import base64
import datetime as dt
import pathlib
import streamlit as st

import db
import queries as q

STATIC = pathlib.Path(__file__).parent / "static"
FAVICON = STATIC / "favicon.png"

# The mark is inlined as a data URI so the sidebar does not depend on Streamlit
# serving a static file, which it only does when staticServing is enabled.
_LOGO_B64 = base64.b64encode((STATIC / "logo.svg").read_bytes()).decode()
LOGO_URI = f"data:image/svg+xml;base64,{_LOGO_B64}"

# --------------------------------------------------------------------- interface
INK = "#0E0F10"
INK_SOFT = "#191A1C"
INK_2 = "#3A3A38"
MUTED = "#84837C"
LIME = "#DDF247"
LIME_DEEP = "#C4DB1E"
CANVAS = "#F2F2EE"
CARD = "#FFFFFF"
LINE = "#E3E3DC"
GRID = "#EDEDE7"

# --------------------------------------------------------------------- data
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
PALETTE = SERIES
SEQUENTIAL = [
    [0.00, "#e8f0fc"], [0.20, "#b7d3f6"], [0.40, "#6da7ec"],
    [0.65, "#2a78d6"], [0.85, "#1c5cab"], [1.00, "#0d366b"],
]

FONT = '-apple-system, "Segoe UI", Inter, Roboto, "Helvetica Neue", Arial, sans-serif'
MONO = '"SF Mono", "Cascadia Mono", "JetBrains Mono", Consolas, monospace'

CSS = f"""
<style>
  :root {{
    --ink:{INK}; --ink-soft:{INK_SOFT}; --ink2:{INK_2}; --muted:{MUTED};
    --lime:{LIME}; --lime-deep:{LIME_DEEP};
    --canvas:{CANVAS}; --card:{CARD}; --line:{LINE};
  }}

  .stApp {{ background: var(--canvas); }}
  .block-container {{ padding-top: 1.6rem; padding-bottom: 5rem; max-width: 1280px; }}
  html, body, [class*="css"] {{ font-family: {FONT}; -webkit-font-smoothing: antialiased; }}

  /* ---------------------------------------------------------------- hero */
  .rm-hero {{
    background: var(--lime); border-radius: 20px;
    padding: 1.95rem 2.15rem 1.75rem; margin: .1rem 0 2rem;
    position: relative; overflow: hidden;
  }}
  .rm-hero::after {{
    content: ""; position: absolute; right: -80px; top: -80px;
    width: 260px; height: 260px; border-radius: 50%; background: rgba(0,0,0,.05);
  }}
  .rm-hero h1 {{
    font-size: 2.5rem !important; font-weight: 680 !important;
    letter-spacing: -.036em; color: var(--ink) !important;
    margin: 0 0 .5rem !important; line-height: 1.04; position: relative; z-index: 1;
  }}
  .rm-hero p {{
    color: #2B2D20; font-size: .955rem; line-height: 1.62;
    max-width: 64ch; margin: 0 0 1.2rem; position: relative; z-index: 1;
  }}
  .rm-chips {{ display: flex; flex-wrap: wrap; gap: .45rem; position: relative; z-index: 1; }}
  .rm-chip {{
    background: var(--ink); color: #EFEFE9; border-radius: 999px;
    padding: .35rem .85rem; font-size: .765rem; font-weight: 530; white-space: nowrap;
  }}
  .rm-chip b {{ color: var(--lime); font-weight: 660; }}

  /* ---------------------------------------------------------------- page head */
  .rm-head {{ margin: .1rem 0 .2rem; }}
  .rm-kicker {{
    display: inline-block; background: var(--lime); color: var(--ink);
    border-radius: 999px; padding: .22rem .72rem; font-size: .672rem;
    font-weight: 680; letter-spacing: .105em; text-transform: uppercase;
    margin-bottom: .75rem;
  }}
  .rm-head h1 {{
    font-size: 2.2rem !important; font-weight: 670 !important;
    letter-spacing: -.033em; color: var(--ink); margin: 0 0 .35rem !important;
  }}
  .rm-sub {{
    color: var(--muted); font-size: .935rem; line-height: 1.62;
    max-width: 70ch; margin: .15rem 0 1.6rem;
  }}

  /* ---------------------------------------------------------------- sections */
  h2 {{
    font-size: 1.23rem !important; font-weight: 650 !important;
    letter-spacing: -.016em; color: var(--ink); margin: 2.7rem 0 .9rem !important;
    display: flex; align-items: center; gap: .62rem;
  }}
  h2::before {{
    content: ""; width: 9px; height: 9px; border-radius: 3px; flex: none;
    background: var(--lime); box-shadow: 0 0 0 3.5px rgba(221,242,71,.3);
  }}
  h3 {{ font-size: 1rem !important; font-weight: 620 !important; color: var(--ink); }}

  /* ---------------------------------------------------------------- metrics */
  [data-testid="stMetric"] {{
    background: var(--card); border: 1px solid var(--line);
    border-radius: 15px; padding: .95rem 1.05rem .9rem;
    transition: box-shadow .16s ease, transform .16s ease, border-color .16s ease;
  }}
  [data-testid="stMetric"]:hover {{
    box-shadow: 0 8px 22px -12px rgba(14,15,16,.28);
    border-color: #D3D3C9; transform: translateY(-1px);
  }}
  [data-testid="stMetricValue"] {{
    font-size: clamp(.98rem, 1.42vw, 1.36rem) !important; font-weight: 660 !important;
    color: var(--ink) !important; letter-spacing: -.028em;
    white-space: normal; line-height: 1.25;
  }}
  [data-testid="stMetricValue"] > div {{ overflow: visible !important; }}
  [data-testid="stMetricLabel"], [data-testid="stMetricLabel"] p,
  [data-testid="stMetricLabel"] > div {{
    font-size: .645rem !important; font-weight: 620 !important;
    letter-spacing: .085em; text-transform: uppercase; color: var(--muted) !important;
    white-space: nowrap !important; overflow: visible !important;
    text-overflow: clip !important; line-height: 1.35;
  }}
  [data-testid="stMetricDelta"] {{ font-size: .755rem !important; color: var(--muted) !important; }}

  /* ---------------------------------------------------------------- reading */
  .rm-note {{
    background: var(--card); border: 1px solid var(--line);
    border-left: 4px solid var(--lime); border-radius: 4px 14px 14px 4px;
    padding: 1rem 1.2rem; margin: 1rem 0 1.7rem;
    font-size: .925rem; line-height: 1.68; color: var(--ink2);
  }}
  .rm-note b {{ color: var(--ink); font-weight: 640; }}

  /* ---------------------------------------------------------------- surfaces */
  [data-testid="stPlotlyChart"] {{
    background: var(--card); border: 1px solid var(--line);
    border-radius: 15px; padding: .9rem 0 .75rem;
    box-sizing: border-box;
  }}
  [data-testid="stPlotlyChart"] > div,
  [data-testid="stPlotlyChart"] .js-plotly-plot,
  [data-testid="stPlotlyChart"] .plot-container {{ width: 100% !important; }}
  [data-testid="stDataFrame"] {{ border: 1px solid var(--line); border-radius: 14px; }}
  [data-testid="stExpander"] {{
    border: 1px solid var(--line); border-radius: 13px; background: var(--card);
  }}
  /* --------------------------------------------------------------- overflow
     One rule for the whole app: nothing is ever silently cut. If content is
     bigger than the box it sits in, the box scrolls. Rounded corners are not
     worth content a reader cannot reach, which is what overflow:hidden on these
     cards cost -- clipped EXPLAIN plans, half-sliced axis labels, and tables
     with their scrollbars removed. */
  [data-testid="stDataFrame"], [data-testid="stTable"], [data-testid="stJson"],
  [data-testid="stExpanderDetails"], [data-testid="stPlotlyChart"],
  [data-testid="stVerticalBlock"], [data-testid="stHorizontalBlock"],
  [data-testid="stMetric"] {{ max-width: 100%; }}

  [data-testid="stTable"], [data-testid="stJson"],
  [data-testid="stExpanderDetails"] {{ overflow-x: auto; }}

  /* Plans and wide SQL must scroll sideways rather than be cut off. */
  [data-testid="stCode"], [data-testid="stCode"] pre,
  [data-testid="stExpander"] pre, .stCodeBlock pre {{
    overflow-x: auto !important; max-width: 100%;
  }}
  [data-testid="stExpander"] [data-testid="stExpanderDetails"] {{ overflow-x: auto; }}
  [data-testid="stExpander"] summary {{ font-size: .875rem; color: var(--ink2); font-weight: 520; }}
  [data-testid="stExpander"] summary:hover {{ color: var(--ink); }}

  .stButton > button {{
    border-radius: 10px; border: 1px solid var(--line); background: var(--card);
    color: var(--ink); font-weight: 570; font-size: .865rem; padding: .38rem 1rem;
    transition: all .14s ease;
  }}
  .stButton > button:hover {{
    background: var(--lime); border-color: var(--lime-deep);
    color: var(--ink); transform: translateY(-1px);
  }}
  .stButton > button[kind="primary"] {{ background: var(--ink); border-color: var(--ink); color: #fff; }}
  .stButton > button[kind="primary"]:hover {{ background: var(--lime); border-color: var(--lime-deep); color: var(--ink); }}

  hr, [data-testid="stDivider"] {{ border-color: var(--line) !important; }}
  code {{ font-family: {MONO}; font-size: .83rem; background: #EFEFE9;
          padding: .1rem .34rem; border-radius: 5px; color: #2B2C2A; }}
  [data-testid="stCode"] {{ border-radius: 12px; }}

  /* ---------------------------------------------------------------- sidebar */
  /* Sidebar colours come from [theme.sidebar] in config.toml, not from here.
     Overriding widget internals by selector is what made the select values
     invisible: the surface went dark while the widget kept its light-theme text
     colour. Only the brand wordmark and the nav plate are styled below, because
     neither is a Streamlit widget. */
  [data-testid="stSidebar"] {{ border-right: none; }}

  /* Sidebar footer: attribution and links, pinned under the filters. */
  .rm-foot {{ padding: .2rem .1rem 0; }}
  .rm-foot .n {{ font-size: .82rem; font-weight: 620; color: #EDEDE8; margin-bottom: .18rem; }}
  .rm-foot .l {{ font-size: .77rem; margin-bottom: .55rem; }}
  .rm-foot .l a {{ color: {LIME}; text-decoration: none; border-bottom: 1px solid rgba(221,242,71,.35); }}
  .rm-foot .l a:hover {{ border-bottom-color: {LIME}; }}
  .rm-foot .m {{ font-size: .715rem; color: #85857D; line-height: 1.65; }}

  /* Brand lockup. Drawn on the nav container because st.navigation emits its
     list before any sidebar content we could write, so a markdown block would
     land underneath the menu. */
  [data-testid="stSidebarNav"]::before {{
    content: "RETAILMIND";
    display: block; color: #fff; font-size: .95rem; font-weight: 680;
    letter-spacing: .012em; padding: .1rem .6rem .1rem 2.55rem; margin-bottom: .9rem;
    background-image: url("{LOGO_URI}");
    background-repeat: no-repeat; background-size: 30px 30px;
    background-position: left center; line-height: 30px;
  }}

  /* Active nav is a lime plate with ink text -- the loudest element in the shell
     and, at ~16:1, the most legible one. */
  [data-testid="stSidebarNav"] a {{ border-radius: 10px; margin-bottom: .12rem; }}
  [data-testid="stSidebarNav"] a span {{ font-size: .875rem; font-weight: 530; color: #B7B7AF; }}
  [data-testid="stSidebarNav"] a:hover {{ background: {INK_SOFT}; }}
  [data-testid="stSidebarNav"] a:hover span {{ color: #fff; }}
  [data-testid="stSidebarNav"] a[aria-current="page"],
  [data-testid="stSidebarNav"] li a[aria-current] {{ background: var(--lime) !important; }}
  [data-testid="stSidebarNav"] a[aria-current="page"],
  [data-testid="stSidebarNav"] a[aria-current="page"] *,
  [data-testid="stSidebarNav"] li a[aria-current] * {{
    color: {INK} !important; fill: {INK} !important; font-weight: 650 !important;
  }}
</style>
"""


def boot():
    """Called once, from the entry point, before any view runs."""
    st.set_page_config(
        page_title="RetailMind",
        page_icon=str(FAVICON) if FAVICON.exists() else "◆",
        layout="wide", initial_sidebar_state="expanded",
    )
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title: str, blurb: str, chips=None):
    """The lime panel. One per page, at the top, and nowhere else."""
    chip_html = "".join(
        f'<div class="rm-chip">{label} <b>{value}</b></div>' for label, value in (chips or [])
    )
    st.markdown(
        f'<div class="rm-hero"><h1>{title}</h1><p>{blurb}</p>'
        f'<div class="rm-chips">{chip_html}</div></div>',
        unsafe_allow_html=True,
    )


def head(kicker: str, title: str, blurb: str):
    """Page header for the views that do not carry the hero."""
    st.markdown(
        f'<div class="rm-head"><span class="rm-kicker">{kicker}</span><h1>{title}</h1></div>',
        unsafe_allow_html=True,
    )
    sub(blurb)


def footer():
    """
    Attribution in the sidebar of every page. A portfolio project with no name on
    it is indistinguishable from a template, and the links are the point: whoever
    opens this should be one click from the source and from the person.
    """
    st.sidebar.divider()
    st.sidebar.markdown(
        '<div class="rm-foot">'
        '<div class="n">Komalpreet Kaur</div>'
        '<div class="l">'
        '<a href="https://komalpreet.me" target="_blank">komalpreet.me</a> · '
        '<a href="https://github.com/Komalpreet2809/RetailMind" target="_blank">Source</a>'
        '</div>'
        '<div class="m">Synthetic retail data modelled on Indian omnichannel '
        'behaviour — heavy-tailed value, festive seasonality, and campaigns with '
        'real holdout groups.<br>PostgreSQL 17 · Neon · Streamlit</div>'
        '</div>',
        unsafe_allow_html=True,
    )


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
    one mark, and a white surface matching every other block on the page.
    """
    fig.update_layout(
        height=height,
        margin=dict(l=18, r=20, t=12, b=34),
        paper_bgcolor=CARD,
        plot_bgcolor=CARD,
        font=dict(family=FONT, size=12, color=INK_2),
        hoverlabel=dict(bgcolor=INK, bordercolor=INK, font_size=12,
                        font_family=FONT, font_color="#F1F1EB"),
        hovermode="x unified",
        showlegend=legend,
        legend=dict(orientation="h", y=1.16, x=0, xanchor="left",
                    bgcolor="rgba(0,0,0,0)", font=dict(size=11.5, color=INK_2)),
        bargap=.3, bargroupgap=.09,
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

    st.sidebar.caption(f"Covers {lo} → {hi}")
    return {"brand": brand, "start": start, "end": end}, pick
