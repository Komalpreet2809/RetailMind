"""
Plan analysis :: rules that read an EXPLAIN ANALYZE tree and say what is wrong.

Deliberately deterministic. A language model asked to review a query plan will
produce something that reads well and is occasionally invented, and the failure
mode is the worst kind -- confident, plausible, wrong. Every finding here is
derived arithmetically from numbers the planner reported, so each one can be
checked against the plan sitting next to it on the page.

What each rule looks for is the same short list an experienced reader checks
first: is it reading the whole table, did the planner believe the wrong thing
about how many rows it would get, is a join being executed once per row, and did
anything spill to disk.
"""

from dataclasses import dataclass, field


@dataclass
class Finding:
    severity: str          # high | medium | low
    title: str
    detail: str
    node: str = ""
    fix: str = ""


SEV_ORDER = {"high": 0, "medium": 1, "low": 2}


def walk(node, depth=0, parent=None):
    """Yield (node, depth, parent) for the whole plan tree, depth-first."""
    yield node, depth, parent
    for child in node.get("Plans", []) or []:
        yield from walk(child, depth + 1, node)


def _rows(node):
    """Actual rows produced by one node, totalled across all its executions."""
    return node.get("Actual Rows", 0) * max(node.get("Actual Loops", 1), 1)


def analyse(plan_json, big_table_rows=200_000):
    """Return (findings, summary) for a Postgres EXPLAIN (ANALYZE, FORMAT JSON)."""
    root = plan_json[0]["Plan"]
    total_ms = plan_json[0].get("Execution Time", 0.0)
    findings: list[Finding] = []

    n_nodes = 0
    shared_read = 0
    shared_hit = 0

    for node, _, parent in walk(root):
        n_nodes += 1
        ntype = node.get("Node Type", "")
        rel = node.get("Relation Name", "")
        label = f"{ntype}{' on ' + rel if rel else ''}"
        loops = max(node.get("Actual Loops", 1), 1)
        actual = node.get("Actual Rows", 0)
        planned = node.get("Plan Rows", 0)
        shared_read += node.get("Shared Read Blocks", 0)
        shared_hit += node.get("Shared Hit Blocks", 0)

        # --- reading the whole table when only a slice is wanted
        if ntype == "Seq Scan":
            removed = node.get("Rows Removed by Filter", 0)
            scanned = actual + removed
            if scanned >= big_table_rows and removed > actual * 4:
                pct = 100.0 * removed / max(scanned, 1)
                findings.append(Finding(
                    "high",
                    f"Sequential scan reads {scanned:,} rows and discards {pct:.0f}%",
                    f"{label} produced {actual:,} rows after throwing away "
                    f"{removed:,}. The filter is doing the work an index should be "
                    f"doing, and the cost of this node grows with the size of the "
                    f"table rather than with the size of the answer.",
                    label,
                    "Index the columns in the WHERE clause. Where the predicate mixes "
                    "equality and a range, put the equality column first.",
                ))
            elif scanned >= big_table_rows and removed == 0:
                findings.append(Finding(
                    "low",
                    f"Full scan of {scanned:,} rows, but nothing is discarded",
                    f"{label} reads the table end to end and keeps almost all of it"
                    f"{f' (across {loops} parallel workers)' if loops > 1 else ''}. "
                    f"That is usually the correct plan for an aggregate over "
                    f"everything -- an index would not help a query that genuinely "
                    f"needs every row.",
                    label,
                    "If this runs often, pre-aggregate it instead of indexing it.",
                ))

        # --- executed once per outer row
        # This is the rule that catches a correlated subquery, which is otherwise
        # invisible: the node itself is a fast index lookup and looks perfectly
        # healthy, and the damage is entirely in how many times it runs. The same
        # test catches a nested loop whose inner side has got out of hand, so it
        # is written against loop count rather than against node type.
        if loops >= 5_000 and (parent is None or max(parent.get("Actual Loops", 1), 1) < loops):
            per = node.get("Actual Total Time", 0.0)
            kind = ("correlated subquery" if node.get("Parent Relationship") == "SubPlan"
                    else "inner side of a join")
            findings.append(Finding(
                "high",
                f"{ntype} executed {loops:,} times",
                f"This node runs once per row of its parent — it is the {kind}. "
                f"Each execution takes {per:.3f} ms, which looks harmless in "
                f"isolation, and {loops:,} of them come to roughly "
                f"{per * loops:,.0f} ms. Cost here is driven by how often the node "
                f"runs, not by how fast it is, so indexing it further will not "
                f"help much.",
                label,
                "Rewrite so the work happens once instead of per row: a window "
                "function, DISTINCT ON, or a grouped aggregate joined back to the "
                "outer query.",
            ))

        # --- the planner believed something false
        # Restricted to scans and joins on purpose. An estimate that is wrong on an
        # aggregate's output is noise -- the node produces a handful of rows and
        # nothing downstream depends on the guess. On a scan or a join it decides
        # the strategy for everything above it, which is where plans go wrong.
        decisive = "Scan" in ntype or "Join" in ntype or ntype == "Nested Loop"
        if decisive and loops == 1 and planned > 0 and actual > 0:
            ratio = max(actual / planned, planned / actual)
            if ratio >= 10 and max(actual, planned) > 1000:
                findings.append(Finding(
                    "medium",
                    f"Row estimate off by {ratio:.0f}× at {ntype}",
                    f"The planner expected {planned:,} rows and got {actual:,}. "
                    f"Estimates drive every choice above this node -- join order, "
                    f"join strategy, whether a sort fits in memory -- so a wrong "
                    f"estimate here can produce a badly wrong plan overall, even "
                    f"when this node itself is quick.",
                    label,
                    "ANALYZE the table. If it stays wrong, raise the statistics "
                    "target on the column, or add extended statistics when two "
                    "columns are correlated.",
                ))

        # --- spilled to disk
        if node.get("Sort Method", "").startswith("external"):
            kb = node.get("Sort Space Used", 0)
            findings.append(Finding(
                "medium",
                f"Sort spilled to disk ({kb:,} kB)",
                "The sort did not fit in work_mem and was written out to temporary "
                "files. Disk sorts are far slower than in-memory ones, and the cost "
                "lands on every execution of this node.",
                label,
                "Raise work_mem for this query, return fewer rows before sorting, or "
                "add an index that already provides the required order.",
            ))

        if node.get("Hash Batches", 1) and node.get("Hash Batches", 1) > 1:
            findings.append(Finding(
                "medium",
                f"Hash join split into {node['Hash Batches']} batches",
                "The hash table did not fit in work_mem, so the join was partitioned "
                "and spilled through temporary files.",
                label,
                "Raise work_mem, or reduce the number of rows reaching the hash build.",
            ))

        # --- bitmap recheck throwing work away
        recheck = node.get("Rows Removed by Index Recheck", 0)
        if recheck and recheck > actual:
            findings.append(Finding(
                "low",
                f"Bitmap recheck discards {recheck:,} rows",
                "The bitmap became lossy, so Postgres had to re-test rows after "
                "fetching whole pages instead of individual tuples.",
                label,
                "Raise work_mem so the bitmap stays exact, or narrow the predicate.",
            ))

    # --- cache behaviour, judged over the whole plan
    total_blocks = shared_read + shared_hit
    if total_blocks > 5000 and shared_read > total_blocks * 0.5:
        findings.append(Finding(
            "low",
            f"{100.0 * shared_read / total_blocks:.0f}% of pages came from outside cache",
            f"{shared_read:,} of {total_blocks:,} blocks were read rather than found "
            f"in shared buffers. On a first run that is expected; if it persists, the "
            f"working set is larger than the cache.",
            "whole plan",
            "Reduce the pages touched — a narrower index, or fewer rows scanned.",
        ))

    findings.sort(key=lambda f: SEV_ORDER[f.severity])

    summary = {
        "total_ms": total_ms,
        "nodes": n_nodes,
        "rows": _rows(root),
        "shared_read": shared_read,
        "shared_hit": shared_hit,
        "scan_types": sorted({
            n.get("Node Type") for n, _, _ in walk(root)
            if "Scan" in n.get("Node Type", "")
        }),
    }
    return findings, summary


def render_tree(node, depth=0, lines=None):
    """A compact indented view of the plan: node, timing, rows planned vs actual."""
    if lines is None:
        lines = []
    ntype = node.get("Node Type", "")
    rel = node.get("Relation Name", "")
    idx = node.get("Index Name", "")
    loops = max(node.get("Actual Loops", 1), 1)
    actual = node.get("Actual Rows", 0)
    planned = node.get("Plan Rows", 0)
    ms = node.get("Actual Total Time", 0.0) * loops

    label = ntype
    if rel:
        label += f" on {rel}"
    if idx:
        label += f" using {idx}"

    est = ""
    if planned and actual:
        ratio = max(actual / planned, planned / actual)
        if ratio >= 10:
            est = f"  ⚠ est {planned:,} vs {actual:,}"

    lines.append(
        f"{'  ' * depth}{'└─ ' if depth else ''}{label}"
        f"   {ms:,.1f} ms   {actual * loops:,} rows"
        f"{f'  ×{loops:,} loops' if loops > 1 else ''}{est}"
    )
    for child in node.get("Plans", []) or []:
        render_tree(child, depth + 1, lines)
    return lines
