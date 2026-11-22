"""Graphviz DOT builders shared by the pages. All user-supplied text is escaped."""

from __future__ import annotations

PALETTE = ["#c7d2fe", "#bbf7d0", "#fde68a", "#fbcfe8", "#bae6fd", "#fed7aa", "#ddd6fe", "#fecdd3", "#d9f99d", "#e5e7eb"]
BADGE_COLORS = ["blue", "green", "orange", "violet", "red", "gray", "primary"]


def esc(text) -> str:
    """Escape text for a double-quoted DOT string (quotes, backslashes, newlines)."""
    return str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\r", " ").replace("\n", " ")


def md_escape(text) -> str:
    """Escape characters that Streamlit markdown would interpret in data-driven labels."""
    out = str(text)
    for ch in ("\\", "*", "_", "`", "[", "]", "$", "<", ">", ":", "#", "|", "~"):
        out = out.replace(ch, "\\" + ch)
    return out


def category_colors(catalog) -> dict[str, str]:
    return {c: PALETTE[i % len(PALETTE)] for i, c in enumerate(catalog.categories)}


def category_badges(catalog) -> dict[str, str]:
    return {c: f":{BADGE_COLORS[i % len(BADGE_COLORS)]}-badge[{md_escape(c)}]" for i, c in enumerate(catalog.categories)}


def agent_flow_dot(active: str | None = None) -> str:
    nodes = [
        ("input", "Student input\\nGoals & interests"),
        ("goal", "Goal agent\\nSets the objective"),
        ("constraint", "Constraint agent\\nFilters valid options"),
        ("planning", "Planning agent\\nBuilds the roadmap"),
        ("adapt", "Adaptation agent\\nKeeps it current"),
        ("guard", "Guardrails\\n+ advisor review"),
        ("out", "Roadmap"),
    ]
    lines = [
        "digraph G {",
        'rankdir=LR; bgcolor=transparent; node [shape=box, style="rounded,filled", fontname=Helvetica, fontsize=11, fillcolor="#eef2ff", color="#6366f1"];',
        'edge [color="#94a3b8"];',
    ]
    for key, label in nodes:
        fill = "#6366f1" if key == active else ("#f1f5f9" if key in ("input", "out") else "#eef2ff")
        font = "white" if key == active else "black"
        lines.append(f'{key} [label="{label}", fillcolor="{fill}", fontcolor="{font}"];')
    lines += [
        "input -> goal -> constraint -> planning -> guard -> out;",
        'out -> adapt [label=" course dropped / goal changed", fontsize=9, style=dashed];',
        "adapt -> planning [style=dashed];",
        'data [label="Catalog · Registrar · Degree audit\\nPass rates · Career outcomes", shape=cylinder, fillcolor="#f8fafc"];',
        "data -> constraint [style=dotted]; data -> planning [style=dotted];",
        "}",
    ]
    return "\n".join(lines)


def roadmap_dot(plan, completed, catalog) -> str:
    courses = catalog.courses
    colors = category_colors(catalog)
    shown = {c for s in plan.semesters for c in s.courses} | set(completed)
    lines = [
        "digraph G {",
        "rankdir=LR; bgcolor=transparent; newrank=true; nodesep=0.15; ranksep=0.45;",
        'node [shape=box, style="rounded,filled", fontname=Helvetica, fontsize=10, color="#64748b"];',
        'edge [color="#94a3b8", arrowsize=0.6];',
    ]
    # One column per term: a header node and its courses share a rank; headers are chained invisibly.
    headers = []
    if completed:
        headers.append("__h_done")
        lines.append('{ rank=same; "__h_done" [label="Transcript", shape=plaintext, style="", fontsize=11];')
        for c in sorted(completed):
            lines.append(f'"{esc(c)}" [label="{esc(c)}", fillcolor="#e2e8f0"];')
        lines.append("}")
    for s in plan.semesters:
        if not s.courses:
            continue
        h = f"__h_{s.index}"
        headers.append(h)
        suffix = " (taken)" if s.history else ""
        lines.append(f'{{ rank=same; "{h}" [label="{esc(s.label)}{suffix}", shape=plaintext, style="", fontsize=11];')
        for c in s.courses:
            pen = ', penwidth=2, color="#dc2626"' if courses[c].hard else ""
            lines.append(f'"{esc(c)}" [label="{esc(c)}\\n{esc(courses[c].name[:18])}", fillcolor="{colors.get(courses[c].category, PALETTE[-1])}"{pen}];')
        lines.append("}")
    for a, b in zip(headers, headers[1:]):
        lines.append(f'"{a}" -> "{b}" [style=invis];')
    for c in sorted(shown):
        for p in courses[c].prereqs:
            if p in shown:
                lines.append(f'"{esc(p)}" -> "{esc(c)}";')
        for co in courses[c].coreqs:
            if co in shown and c < co:
                lines.append(f'"{esc(c)}" -> "{esc(co)}" [dir=both, style=dashed, color="#f59e0b"];')
    lines.append("}")
    return "\n".join(lines)


def occupation_network_dot(graph, table_rows) -> str:
    info = {r["Occupation"]: r for r in table_rows}
    lines = [
        "graph G {",
        "layout=neato; overlap=false; splines=true; bgcolor=transparent;",
        'node [shape=box, style="rounded,filled", fontname=Helvetica, fontsize=10, color="#64748b"];',
    ]
    for n in graph.nodes:
        r = info.get(n, {})
        risk = graph.nodes[n]["risk"]
        fill = "#fecaca" if risk >= 0.4 else ("#fde68a" if risk >= 0.2 else "#bbf7d0")
        lines.append(f'"{esc(n)}" [label="{esc(n)}\\n{r.get("Workers", 0)} workers · {r.get("Open vacancies", 0)} open", fillcolor="{fill}"];')
    for a, b, d in graph.edges(data=True):
        lines.append(f'"{esc(a)}" -- "{esc(b)}" [label="{d["weight"]:.2f}", fontsize=8, color="#94a3b8"];')
    lines.append("}")
    return "\n".join(lines)
