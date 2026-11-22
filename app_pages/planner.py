import numpy as np
import pandas as pd
import streamlit as st

from core.abm import match_score, skills_from_courses
from core.agents import Event, Orchestrator
from core.state import data_badge
from core.viz import category_badges, md_escape, roadmap_dot

ss = st.session_state
cat = ss.catalog
mk = ss.market
req = cat.requirements
CAT_BADGE = category_badges(cat)


def course_label(code: str) -> str:
    return f"{code} · {cat.courses[code].name}" if code in cat.courses else code


RESOURCE_ICONS = {"reading": ":material/menu_book:", "video": ":material/play_circle:", "course": ":material/school:",
                  "practice": ":material/edit_note:"}


def safe_url(url: str) -> str:
    """Make a URL safe inside a markdown link."""
    return url.strip().replace(" ", "%20").replace("(", "%28").replace(")", "%29")


def resources_md(code: str, compact: bool = True) -> str:
    """Markdown links for a subject: curated links first, then one search link per learning site."""
    res = cat.resources_for(code)
    if not res:
        return ""
    curated = [r for r in res if r["kind"] == "curated"]
    search = [r for r in res if r["kind"] == "search"]
    parts = [f"{RESOURCE_ICONS.get(r['type'], ':material/link:')} [{md_escape(r['title'])}]({safe_url(r['url'])})" for r in curated]
    if search:
        links = " · ".join(f"[{md_escape(r['title'])}]({safe_url(r['url'])})" for r in search)
        parts.append(f":material/search: {links}")
    return ":small[" + "  \n".join(parts) + "]" if compact else "  \n".join(parts)


def render_steps(steps):
    for step in steps:
        with st.status(f"**{step.agent}** — {step.action}", type="step", state="complete" if step.ok else "error"):
            for d in step.details:
                st.markdown(f"- {d}")


st.title("Roadmap planner", anchor=False)
st.caption(f"{req.program} · {len(cat.courses)} courses · {len(cat.careers)} career goals · {data_badge()}")

# ------------------------------------------------------------------ student input
first_career = next(iter(cat.careers.values()))
default_goal = f"I want to become a {first_career.name.lower()} and graduate in 4 years."
# Keys let the Tutorial page pre-fill an example goal.
ss.setdefault("goal_text", default_goal)
if ss.get("goal_career") not in ["Infer from my text"] + list(cat.careers):
    ss.goal_career = "Infer from my text"
if ss.pop("tutorial_prefilled", False):
    st.info("Example goal from the tutorial is filled in. Press **Generate roadmap**.", icon=":material/school:")
with st.form("student"):
    left, right = st.columns([3, 2], gap="large")
    with left:
        text = st.text_area("Your goals", key="goal_text", height=110,
                            help="Mention a career, a timeline ('3.5 years', '7 semesters'), load ('part-time') or interests.")
        career = st.selectbox("Career goal", ["Infer from my text"] + list(cat.careers), key="goal_career")
        interests = st.pills("Interests", cat.interest_tags, selection_mode="multi")
        completed = st.multiselect("Already completed (transcript)", list(cat.courses), format_func=course_label)
    with right:
        c1, c2 = st.columns(2)
        start_season = c1.segmented_control("First term", list(req.seasons), default=req.seasons[0], required=True)
        start_year = c2.number_input("Year", 2000, 2100, 2026)
        per_year = len(req.seasons)
        target = st.slider("Target terms to graduate", 1, 16, min(16, 4 * per_year))
        max_credits = st.slider("Max credits per term", 3, 30, 15)
        avoid_hard = st.toggle(
            "Limit historically difficult courses",
            help=f"At most {req.max_hard_if_avoiding} course(s) with a pass rate under {req.hard_threshold:.0%} per term",
        )
        balance = st.toggle("Balance load across the timeline", value=True, help="Off = pack courses for the earliest graduation")
    submitted = st.form_submit_button("Generate roadmap", type="primary", icon=":material/auto_awesome:")

if submitted:
    ss.orch = Orchestrator(cat)
    form = {
        "career": None if career == "Infer from my text" else career,
        "interests": interests, "completed": completed, "start_season": start_season, "start_year": start_year,
        "target_semesters": target, "max_credits": max_credits, "avoid_hard": avoid_hard, "balance_load": balance,
    }
    obj, plan, steps, issues = ss.orch.run(text, form)
    ss.objective, ss.plan, ss.issues = obj, plan, issues
    ss.trace = [("Initial plan", steps)]
    ss.blocked, ss.last_diff, ss.approved = set(), None, False
    ss.versions = [("v1 · initial", plan)]

if ss.plan is None:
    st.info("Fill in the form and press **Generate roadmap** to run the four agents.", icon=":material/info:")
    st.stop()

obj, plan, issues = ss.objective, ss.plan, ss.issues
errors = [m for s, m in issues if s == "error"]

# -------------------------------------------------------------------- summary
with st.container(horizontal=True):
    st.metric("Projected graduation", plan.graduation or "Not reachable", border=True)
    st.metric("Terms", f"{plan.term_count} / {obj.target_semesters} target", border=True)
    st.metric("Credits planned", sum(s.credits for s in plan.future), border=True)
    st.metric("Career goal", obj.career.name, border=True)
    st.metric("Guardrails", "Passed" if not errors else f"{len(errors)} issue(s)", border=True)

with st.expander("Agent trace", icon=":material/smart_toy:", expanded=True):
    for title, steps in ss.trace:
        st.markdown(f"**{title}**")
        render_steps(steps)

if ss.last_diff:
    d = ss.last_diff
    with st.container(border=True):
        st.markdown("#### :material/compare_arrows: What changed in the last re-plan")
        rows = [{"Change": "Moved", "Course": course_label(c), "From": a, "To": b} for c, a, b in d["moved"]]
        rows += [{"Change": "Added", "Course": course_label(c), "From": "", "To": b} for c, b in d["added"]]
        rows += [{"Change": "Removed", "Course": course_label(c), "From": a, "To": ""} for c, a in d["removed"]]
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, alt="Courses moved, added or removed by the re-plan")
        else:
            st.caption("No courses moved.")

# -------------------------------------------------------------------- roadmap
st.subheader("Term-by-term roadmap", anchor=False)
show_res = st.toggle("Show study resources under each subject", value=True, key="show_resources",
                     disabled=not (cat.resources or cat.resource_links),
                     help="Links come from the Course resources and Resource search links datasets (Data manager)")
per_row = 4
for i in range(0, len(plan.semesters), per_row):
    cols = st.columns(per_row)
    for col, s in zip(cols, plan.semesters[i:i + per_row]):
        with col.container(border=True, height="stretch"):
            tag = " :gray-badge[taken]" if s.history else ""
            st.markdown(f"**{md_escape(s.label)}**{tag}  \n:small[{s.credits} credits]")
            if not s.courses:
                st.caption(s.note or "No courses")
            for c in s.courses:
                hard = " :red-badge[hard]" if cat.courses[c].hard else ""
                st.markdown(f"**{md_escape(c)}** {md_escape(cat.courses[c].name)}  \n{CAT_BADGE.get(cat.courses[c].category, '')}{hard}")
                if show_res:
                    links = resources_md(c)
                    if links:
                        st.markdown(links)

tab_graph, tab_table, tab_res, tab_valid, tab_fit = st.tabs(
    [":material/account_tree: Prerequisite graph", ":material/table: Course table", ":material/library_books: Study resources",
     ":material/verified: Validation", ":material/work: Career fit"]
)
with tab_graph:
    st.graphviz_chart(roadmap_dot(plan, obj.completed, cat), width="stretch", alt="Prerequisite graph of the roadmap grouped by term")
    st.caption("Colours = course category · red border = historically difficult · dashed orange = co-requisite")

with tab_table:
    rows = []
    for s in plan.semesters:
        for c in s.courses:
            v = cat.courses[c]
            rows.append({
                "Term": s.label, "Status": "Taken" if s.history else "Planned", "Code": c, "Course": v.name,
                "Credits": v.credits, "Category": v.category, "Pass rate": v.pass_rate,
                "Prerequisites": ", ".join(v.prereqs), "Why": plan.rationale.get(c, "Retake / previously selected"),
                "Main resource": (cat.resources_for(c) or [{"url": None}])[0]["url"],
                "All resources": " | ".join(f"{r['title']}: {r['url']}" for r in cat.resources_for(c)),
            })
    df = pd.DataFrame(rows)
    st.dataframe(
        df.drop(columns=["All resources"]), hide_index=True,
        column_config={
            "Pass rate": st.column_config.ProgressColumn(min_value=0, max_value=1, format="percent"),
            "Main resource": st.column_config.LinkColumn(display_text="Open"),
        },
        alt="Every course in the roadmap with its term, reason and main study resource",
    )
    st.download_button("Download roadmap CSV (with resource links)", df.to_csv(index=False), "roadmap.csv", "text/csv", icon=":material/download:")

with tab_res:
    if not (cat.resources or cat.resource_links):
        st.info("No resources configured. Add them under Course resources / Resource search links in the Data manager.", icon=":material/info:")
    for s in plan.semesters:
        if not s.courses:
            continue
        st.markdown(f"#### {md_escape(s.label)}" + (" :gray-badge[taken]" if s.history else ""))
        for c in s.courses:
            with st.container(border=True):
                st.markdown(f"**{md_escape(c)} · {md_escape(cat.courses[c].name)}**")
                st.markdown(resources_md(c, compact=False) or "No resources for this subject.")

with tab_valid:
    if not issues:
        st.success("Every prerequisite, co-requisite, offering, credit-limit and degree-audit check passed.", icon=":material/check_circle:")
    for sev, msg in issues:
        (st.error if sev == "error" else st.warning)(msg)
    st.markdown("**Human review**")
    is_advisor = ss.user.get("role") in ("advisor", "admin")
    if ss.approved:
        st.success(f"Approved by advisor {ss.approved}. The roadmap can be released to the student.", icon=":material/how_to_reg:")
    elif not is_advisor:
        st.caption("Only advisor or admin accounts can approve a roadmap. Ask your advisor to sign in and review it.")
    elif st.button("Approve as advisor", icon=":material/how_to_reg:", disabled=bool(errors),
                   help="Fix the errors above first" if errors else None):
        ss.approved = ss.user["name"]
        st.rerun()

with tab_fit:
    if not mk.tag_skills:
        st.info("Add a course-to-skill mapping in the Data manager to see career fit.", icon=":material/info:")
    else:
        codes = list(obj.completed) + [c for s in plan.semesters for c in s.courses]
        skills = skills_from_courses(codes, cat, mk)
        ss.roadmap_skills = tuple(float(x) for x in skills)

        def alignment(r):
            r = np.array(r)
            d = np.linalg.norm(skills) * np.linalg.norm(r)
            return float(skills @ r / d) if d else 0.0

        fit = pd.DataFrame({
            "Occupation": [o.name for o in mk.occupations],
            "Profile alignment": [alignment(o.req) for o in mk.occupations],
            "Hiring-bar coverage": [match_score(skills, np.array(o.req)) for o in mk.occupations],
        }).sort_values("Profile alignment", ascending=False)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Best-aligned occupations**")
            st.dataframe(fit, hide_index=True, column_config={
                "Profile alignment": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f", help="Cosine similarity between your skill profile and the role's requirements"),
                "Hiring-bar coverage": st.column_config.ProgressColumn(min_value=0, max_value=1, format="percent", help="Share of required skill mass you cover"),
            }, alt="Occupations ranked by how well the roadmap skill profile aligns")
        with c2:
            st.markdown("**Skill profile implied by the roadmap**")
            st.bar_chart(pd.DataFrame({"Skill": list(mk.skills), "Level": skills}), x="Skill", y="Level", alt="Skill profile implied by the roadmap")
        st.caption("Skill vector from the course-to-skill mapping. Use it in **Career simulation** to test this graduate in the job market.")

# ----------------------------------------------------------------- adaptation
st.subheader("Something changed? Let the Adaptation agent re-plan", anchor=False)
future = [s for s in plan.semesters if not s.history and s.courses]
if not future:
    st.caption("Nothing left to plan.")
    st.stop()

with st.container(border=True):
    kind = st.segmented_control(
        "Event", ["Dropped / failed a course", "Section is full", "Course cancelled", "Goal changed"],
        default="Dropped / failed a course", required=True,
    )
    c1, c2 = st.columns(2)
    by_index = {s.index: s for s in future}
    term = by_index[c1.selectbox("When", list(by_index), format_func=lambda i: by_index[i].label)]
    course = new_career = None
    if kind in ("Dropped / failed a course", "Section is full"):
        course = c2.selectbox("Course", term.courses, format_func=course_label)
    elif kind == "Course cancelled":
        options = sorted({c for s in future if s.index >= term.index for c in s.courses if c not in cat.required})
        if options:
            course = c2.selectbox("Course (non-required)", options, format_func=course_label)
        else:
            c2.caption("No optional courses planned from this term on.")
    else:
        others = [c for c in cat.careers if c != obj.career.name]
        new_career = c2.selectbox("New career goal", others) if others else None

    disabled = (kind == "Course cancelled" and course is None) or (kind == "Goal changed" and new_career is None)
    if st.button("Re-plan", type="primary", icon=":material/autorenew:", disabled=disabled):
        ev_kind = {"Dropped / failed a course": "dropped", "Section is full": "full", "Course cancelled": "cancelled", "Goal changed": "goal_change"}[kind]
        ev = Event(ev_kind, term.index, course=course, new_career=new_career)
        new_obj, new_plan, steps, new_issues, diff = ss.orch.replan(obj, plan, ev, ss.blocked)
        ss.blocked = diff.pop("blocked")
        ss.objective, ss.plan, ss.issues, ss.last_diff, ss.approved = new_obj, new_plan, new_issues, diff, False
        what = f"{kind}: {course or new_career} ({term.label})"
        ss.trace.append((f"Re-plan · {what}", steps))
        ss.versions.append((f"v{len(ss.versions) + 1} · {what}", new_plan))
        st.rerun()

if len(ss.versions) > 1:
    st.caption("Plan versions: " + " → ".join(f"{v} (grad {p.graduation or 'n/a'})" for v, p in ss.versions))
