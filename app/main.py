"""
RetailMind :: entry point and navigation.

Streamlit's magic `pages/` folder names each nav entry after its filename, which
labelled the first item "main" and forced digit prefixes on the rest to control
ordering. Declaring the pages here instead means the sidebar reads as a set of
titled sections, and the files can be named for what they contain.

Everything global happens once, here: page config, the stylesheet, and the order
of the sections. Views are plain scripts that assume both are already in place.
"""

import streamlit as st

import ui

ui.boot()

NAV = st.navigation([
    st.Page("views/overview.py", title="Overview", icon=":material/dashboard:", default=True),
    st.Page("views/segments.py", title="Segments", icon=":material/group:"),
    st.Page("views/retention.py", title="Retention", icon=":material/replay:"),
    st.Page("views/campaigns.py", title="Campaigns", icon=":material/campaign:"),
    st.Page("views/query_lab.py", title="Query Lab", icon=":material/bolt:"),
    st.Page("views/plan_doctor.py", title="Plan Doctor", icon=":material/stethoscope:"),
])

NAV.run()
