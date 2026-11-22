import pandas as pd
import streamlit as st

from core.curriculum import (
    branches, get_university, load_curriculum, load_study_sites, load_syllabus, nptel_url, search_url, semesters,
    step_title, subjects, topic_query, youtube_url,
)
from core.resources import is_dsa, recommended
from core.study_agents import AGENT_NAMES, plan_rows, run_agents
from core.viz import md_escape

ss = st.session_state
uni = get_university(ss.get("current_uni", "")) or get_university("amrita")
if uni is None:
    st.info("No university is loaded.", icon=":material/info:")
    st.stop()


@st.cache_data(show_spinner=False)
def _data(slug: str, stamp: float):
    u = get_university(slug)
    return load_curriculum(u), load_syllabus(u)


df, syllabus = _data(uni.slug, (uni.path / "curriculum.csv").stat().st_mtime)
links = load_study_sites()
KIND_ICON = {"Theory": ":material/menu_book:", "Lab": ":material/science:", "Project": ":material/engineering:",
             "Elective": ":material/alt_route:", "Activity": ":material/groups:"}
SITE_ICON = {"W3Schools": ":material/code:", "GeeksforGeeks": ":material/terminal:", "Striver": ":material/fitness_center:",
             "YouTube": ":material/smart_display:"}
AGENT_ICON = dict(zip(AGENT_NAMES, [":material/person:", ":material/list_alt:", ":material/flag:",
                                    ":material/calendar_month:", ":material/link:", ":material/verified:"]))

st.title(uni.short_name, anchor=False)
st.caption(f"{uni.name} · pick your branch and semester to see every subject, its study resources and a learning "
           "roadmap, or let the study agents build your weekly plan." + (f" Added by {uni.added_by_name}." if uni.added_by_name else ""))

if df.empty:
    st.info("This university has no courses yet.", icon=":material/info:")
    st.stop()

all_branches = branches(df)
bkey, skey = f"sem_branch_{uni.slug}", f"sem_number_{uni.slug}"
c1, c2 = st.columns([2, 3])
branch = c1.selectbox("Branch", all_branches, key=bkey)
sems = semesters(df, branch)
if ss.get(skey) not in sems:
    ss[skey] = sems[0]
semester = c2.segmented_control(uni.term_word, sems, key=skey, format_func=uni.term_label,
                                selection_mode="single", width="stretch")
if semester is None:
    st.stop()

subs = subjects(df, syllabus, branch, semester)
credits = sum(s.credit_value for s in subs)
with st.container(horizontal=True):
    st.metric("Subjects", sum(not s.is_elective_slot for s in subs), border=True)
    st.metric("Elective slots", sum(s.is_elective_slot for s in subs), border=True)
    st.metric("Labs", sum(s.kind == "Lab" for s in subs), border=True)
    st.metric("Credits", f"{credits:g}" if credits else "Not published", border=True)

tab_subjects, tab_agents = st.tabs([":material/menu_book: Subjects and roadmaps", ":material/smart_toy: Study agents"])

# ------------------------------------------------------------------ subjects
with tab_subjects:
    show_roadmaps = st.toggle("Open every learning roadmap", value=False, key="sem_expand_all")
    for s in subs:
        with st.container(border=True):
            head, meta = st.columns([3, 2], vertical_alignment="center")
            name = f"{md_escape(s.title)}" + (f" · `{s.code}`" if s.code else "")
            head.markdown(f"##### {KIND_ICON[s.kind]} {name}")
            badges = [f":blue-badge[{md_escape(s.category)}]"] if s.category else []
            if s.ltp:
                badges.append(f":gray-badge[L-T-P {s.ltp}]")
            if s.credits:
                badges.append(f":green-badge[{s.credits} credits]" if s.credit_value else f":gray-badge[{s.credits}]")
            badges.append(f":violet-badge[{s.kind}]")
            meta.markdown(" ".join(badges))

            if s.is_elective_slot:
                st.caption("Choose one elective for this slot from your department's elective list. Talk to your faculty "
                           "advisor about which basket fits your goals.")
                continue

            picks = recommended(s.title)
            st.markdown(":material/star: **Recommended:** " + " · ".join(
                f"{SITE_ICON.get(site, '')} [{md_escape(site)}: {md_escape(label)}]({url})" for site, label, url in picks))
            if is_dsa(s.title):
                st.caption("Practise the matching topics from Striver's A2Z DSA sheet alongside each roadmap step.")
            if s.resources:
                st.markdown(f":material/school: **{md_escape(uni.short_name)} recommends:** " + " · ".join(
                    f"[{md_escape(label)}]({url})" for label, url in s.resources))
            course_links = " · ".join(f"[{md_escape(n)}]({search_url(t, s.title)})" for n, t in links)
            st.markdown(f":material/search: **More study links:** [NPTEL lectures]({nptel_url(s.title)}) · {course_links}")
            if s.project:
                st.caption(f":material/construction: Course project: {md_escape(s.project)}")

            if s.outline:
                label = (f"Learning roadmap: {len(s.outline)} steps" if s.has_official_syllabus
                         else f"General learning roadmap: {len(s.outline)} steps")
                with st.expander(label, icon=":material/route:", expanded=show_roadmaps):
                    if not s.has_official_syllabus:
                        st.caption("No official syllabus was published for this subject, so this is a general study "
                                   "outline. Follow your class notes for the exact topics.")
                    for i, unit in enumerate(s.outline, 1):
                        q = topic_query(s.title, unit)
                        st.markdown(f"**Step {i}: {md_escape(step_title(unit))}**")
                        st.markdown(md_escape(unit))
                        st.markdown(f":material/play_circle: [Watch videos on this step]({youtube_url(q)}) · "
                                    f"[NPTEL]({nptel_url(q)})")
                        if i < len(s.outline):
                            st.divider()
            elif s.kind == "Lab":
                st.caption("Lab course: follow the experiments your lab instructor gives, and revise the matching theory subject.")
            elif s.kind == "Project":
                st.caption("Project work: plan milestones with your guide and keep a weekly log.")
            elif s.kind == "Activity":
                st.caption("Activity or seminar: take part through the semester. There's nothing to study for an exam.")
            else:
                st.caption("The syllabus doesn't list units for this subject, so there is no step-by-step roadmap.")

            if s.textbooks:
                with st.expander("Textbooks", icon=":material/library_books:"):
                    for b in s.textbooks:
                        st.markdown(f"- {md_escape(b)}")

    table = pd.DataFrame([dict(Code=s.code, Subject=s.title, Category=s.category, LTP=s.ltp, Credits=s.credits, Type=s.kind)
                          for s in subs])
    st.download_button("Download this semester (CSV)", table.to_csv(index=False).encode(),
                       f"{uni.slug}_{branch.replace(' ', '_')}_sem{semester}.csv", "text/csv", icon=":material/download:")
    if uni.source:
        st.caption(f"Source: {uni.source}. Check with your department for the latest version.")

# -------------------------------------------------------------------- agents
with tab_agents:
    st.markdown(
        "Six agents work together on this semester: the **Profile agent** reads your goal and time, the **Syllabus agent** "
        "splits every unit into topics, the **Priority agent** ranks subjects for your goal, the **Scheduler agent** builds "
        "a week-by-week plan, the **Resource agent** adds study links, and the **Review agent** checks the plan."
    )
    with st.form("agents_form"):
        goal = st.text_input("Your goal (optional)", key="agent_goal",
                             placeholder="e.g. AI/ML placements, GATE, core electronics, robotics, software developer job")
        f1, f2, f3 = st.columns(3)
        weeks = f1.number_input("Weeks in the semester", 6, 26, 16, key="agent_weeks")
        hours = f2.number_input("Study hours per week (outside class)", 4, 60, 20, key="agent_hours")
        rev = f3.number_input("Revision weeks before exams", 0, 6, 2, key="agent_rev")
        go = st.form_submit_button("Run the agents", type="primary", icon=":material/smart_toy:")
    run_key = (uni.slug, branch, semester)
    if go:
        ss.agent_run = (run_key, run_agents(subs, goal, int(weeks), float(hours), int(rev)))
    if ss.get("agent_run") and ss.agent_run[0] == run_key:
        bb = ss.agent_run[1]
        with st.expander("Agent trace: what each agent did", icon=":material/account_tree:", expanded=True):
            for agent, summary, details in bb.trace:
                st.markdown(f"{AGENT_ICON.get(agent, ':material/smart_toy:')} **{agent}:** {md_escape(summary)}")
                for d in details[:12]:
                    st.caption(md_escape(d))
        for sev, msg in bb.issues:
            getattr(st, {"error": "error", "warning": "warning"}.get(sev, "info"))(msg)

        if bb.subject_scores:
            st.subheader("Priorities for your goal", anchor=False)
            pri = pd.DataFrame(
                [dict(Subject=t, Priority=sc, Why="; ".join(r),
                      Hours=sum(x.hours for x in bb.topics if x.subject == t)) for t, (sc, r) in bb.subject_scores.items()]
            ).sort_values("Priority", ascending=False)
            st.dataframe(pri, hide_index=True, width="stretch", column_config={
                "Priority": st.column_config.ProgressColumn(min_value=0, max_value=3, format="%.2f"),
                "Hours": st.column_config.NumberColumn("Planned hours", format="%.1f h")})

        if bb.weeks:
            st.subheader("Your weekly study plan", anchor=False)
            chart = pd.DataFrame({"Week": [f"W{i:02d}" for i in range(1, len(bb.week_hours) + 1)], "Hours": bb.week_hours})
            st.bar_chart(chart, x="Week", y="Hours", height=180)
            for w, topics in enumerate(bb.weeks, 1):
                with st.expander(f"Week {w}: {bb.week_hours[w - 1]:g} h · {len(topics)} topics", icon=":material/event:"):
                    for t in topics:
                        link_md = " · ".join(f"[{md_escape(k)}]({u})" for k, u in t.links.items())
                        st.markdown(f"- **{md_escape(t.subject)}** (step {t.step}): {md_escape(t.text)} · *{t.hours:g} h* · {link_md}")
            for r in range(bb.profile.revision_weeks):
                n = len(bb.weeks) + r + 1
                with st.expander(f"Week {n}: revision", icon=":material/replay:"):
                    st.markdown("Revise every subject, redo the hardest topics and solve previous exam papers.")
            plan_csv = pd.DataFrame(plan_rows(bb)).to_csv(index=False).encode()
            st.download_button("Download the study plan (CSV)", plan_csv,
                               f"{uni.slug}_{branch.replace(' ', '_')}_sem{semester}_plan.csv", "text/csv",
                               icon=":material/download:")
    else:
        st.caption("Fill in the form and press **Run the agents**.")
