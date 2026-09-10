"""
Plan Doctor :: paste a query, get its execution plan read back to you.

The Query Lab shows five bottlenecks I already found. This page is the tool that
finds them. Write any SELECT against the warehouse and it runs EXPLAIN ANALYZE,
walks the plan tree, and reports what is actually wrong in words -- sequential
scans that discard most of what they read, row estimates the planner got badly
wrong, nested loops running their inner side tens of thousands of times, sorts
spilling to disk.

Every finding is arithmetic on numbers the planner reported, not a language model
guessing. The plan is shown next to the findings so any of them can be checked.
"""

import streamlit as st

import db
import plandoc
import ui


st.title("Plan Doctor")
ui.sub(
    "Paste a SELECT against the warehouse. It runs EXPLAIN ANALYZE and tells you "
    "what the planner did, and where the time went."
)

EXAMPLES = {
    "— pick an example —": "",
    "Seq scan discarding 99% of what it reads": """
SELECT count(*), round(sum(amount)) AS revenue
FROM orders
WHERE channel = 'app'
  AND items > 6
""".strip(),
    "Correlated subquery, one execution per row": """
SELECT o.customer_id, o.order_id, o.amount
FROM orders o
WHERE o.customer_id <= 2000
  AND o.order_date = (
        SELECT max(o2.order_date) FROM orders o2
        WHERE o2.customer_id = o.customer_id
  )
""".strip(),
    "The same question, answered in one pass": """
SELECT DISTINCT ON (o.customer_id) o.customer_id, o.order_id, o.amount
FROM orders o
WHERE o.customer_id <= 2000
ORDER BY o.customer_id, o.order_date DESC
""".strip(),
    "A big sort with no index to lean on": """
SELECT customer_id, sum(amount) AS spend
FROM orders
GROUP BY customer_id
ORDER BY spend DESC
LIMIT 50
""".strip(),
    "Aggregate over everything (an index cannot help)": """
SELECT date_trunc('month', order_date)::date AS month,
       count(*) AS orders, round(sum(amount)) AS revenue
FROM orders
GROUP BY 1
ORDER BY 1
""".strip(),
}

pick = st.selectbox("Examples", list(EXAMPLES.keys()))
default = EXAMPLES[pick] or st.session_state.get("pd_sql", EXAMPLES[
    "Seq scan discarding 99% of what it reads"])

sql = st.text_area("SQL", value=default, height=190, key="pd_sql_box")

c1, c2 = st.columns([1, 5])
go = c1.button("Explain", type="primary")
c2.caption(
    "Read-only: the statement must be a single SELECT or WITH, it runs inside a "
    "READ ONLY transaction, and a 15-second timeout kills anything that runs away. "
    "Tables available: `orders`, `customers`, `brands`, `stores`, `campaigns`, "
    "`campaign_sends`, and the `mv_*` rollups."
)

if go:
    try:
        with st.spinner("Running EXPLAIN ANALYZE…"):
            plan = db.safe_explain_json(sql)
    except db.UnsafeSQL as e:
        st.warning(str(e))
        st.stop()
    except Exception as e:  # noqa: BLE001 - the database's own message is the useful part
        st.error(f"{type(e).__name__}: {e}")
        st.stop()

    findings, summary = plandoc.analyse(plan)

    m = st.columns(4)
    m[0].metric("Execution time", f"{summary['total_ms']:,.1f} ms")
    m[1].metric("Rows returned", f"{summary['rows']:,}")
    m[2].metric("Plan nodes", summary["nodes"])
    m[3].metric("Pages read / hit", f"{summary['shared_read']:,} / {summary['shared_hit']:,}")

    if summary["scan_types"]:
        st.caption("Scan types used: " + ", ".join(f"`{s}`" for s in summary["scan_types"]))

    st.header("Diagnosis")
    if not findings:
        st.success(
            "Nothing flagged. No scan is discarding most of what it reads, the "
            "planner's row estimates are close to reality, nothing spilled to disk, "
            "and no join is re-running its inner side excessively."
        )
    else:
        icon = {"high": "🔴", "medium": "🟠", "low": "🔵"}
        for f in findings:
            with st.container(border=True):
                st.markdown(f"{icon[f.severity]} **{f.title}**")
                st.markdown(f.detail)
                if f.fix:
                    st.markdown(f"**What to do:** {f.fix}")
                if f.node:
                    st.caption(f"at: `{f.node}`")

    st.header("Plan tree")
    st.code("\n".join(plandoc.render_tree(plan[0]["Plan"])), language="text")

    with st.expander("Raw plan JSON"):
        st.json(plan)

st.divider()
st.caption(
    "The rules live in `app/plandoc.py` — sequential scans with high discard, row "
    "estimates off by 10× or more, nested loops with large inner loop counts, "
    "external sorts and multi-batch hashes, lossy bitmap rechecks, and cache miss "
    "ratio across the whole plan."
)
