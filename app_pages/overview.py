import streamlit as st

from core import settings
from core.state import data_badge
from core.viz import agent_flow_dot

ss = st.session_state
cat, mk = ss.catalog, ss.market
cfg = settings.load()
can_edit_data = ss.user["role"] in cfg["data_manager_roles"]


@st.dialog(f"Welcome to {cfg['app_name']}", icon=":material/waving_hand:")
def welcome():
    st.markdown(f"Hi **{ss.user['name']}**! " + cfg["welcome_message"])
    with st.container(horizontal=True):
        if st.button("Start the tutorial", type="primary", icon=":material/school:"):
            st.switch_page("app_pages/tutorial.py")
        if st.button("Explore on my own"):
            st.rerun()


if not ss.get("welcomed"):
    ss.welcomed = True  # show once per session
    if cfg["show_welcome"]:
        welcome()

st.title(cfg["app_name"], anchor=False)
st.caption(f"Signed in as {ss.user['name']} ({ss.user['role']})")
st.markdown(cfg["overview_intro"])

with st.container(horizontal=True):
    st.page_link("app_pages/tutorial.py", label="New here? Start the tutorial", icon=":material/school:")
    st.page_link("app_pages/planner.py", label="Build a roadmap", icon=":material/route:")
    st.page_link("app_pages/simulation.py", label="Run the career simulation", icon=":material/hub:")
    st.page_link("app_pages/experiments.py", label="Compare scenarios", icon=":material/science:")
    if can_edit_data:
        st.page_link("app_pages/data.py", label="Use your own data", icon=":material/database:")
    if ss.user["role"] == "admin":
        st.page_link("app_pages/admin.py", label="Admin", icon=":material/admin_panel_settings:")

with st.container(horizontal=True):
    st.metric("Courses", len(cat.courses), border=True)
    st.metric("Career goals", len(cat.careers), border=True)
    st.metric("Occupations", len(mk.occupations), border=True)
    st.metric("Skills", len(mk.skills), border=True)
    st.metric("Training courses", len(mk.training), border=True)
st.caption(f"Program: {cat.requirements.program} · {data_badge()}")

st.subheader("How the agents collaborate", anchor=False)
st.graphviz_chart(agent_flow_dot(), width="stretch", alt="Flow from student input through Goal, Constraint and Planning agents to guardrails and the roadmap, with the Adaptation agent looping back")

cols = st.columns(4)
agents = [
    (":material/flag:", "Goal agent", "Parses free-text goals, transcript and preferences into a structured objective (career track, interests, timeline, load)."),
    (":material/rule:", "Constraint agent", "Enforces prerequisites, co-requisites, seasonal offerings, seat limits, credit caps and the degree audit."),
    (":material/account_tree:", "Planning agent", "Chooses electives for the career goal, then runs critical-path list scheduling over valid schedules."),
    (":material/autorenew:", "Adaptation agent", "Re-plans end-to-end when a course is dropped, a section fills, a course is cancelled or the goal changes."),
]
for col, (icon, name, text) in zip(cols, agents):
    with col.container(border=True, height="stretch"):
        st.markdown(f"#### {icon} {name}")
        st.caption(text)

st.subheader("Technical stack in this prototype", anchor=False)
st.table(
    {
        "Deck component": ["LLM reasoning layer", "Agent orchestration", "Tool & API integrations", "Guardrails & validation", "Agent-based simulation"],
        "In this app": [
            "Deterministic keyword goal interpreter (swap point for a tool-calling LLM)",
            "`Orchestrator` sequences hand-offs and keeps shared state",
            "Uploadable catalog, requirements, careers and registrar-seat datasets (Data manager)",
            "Dataset validation + independent re-validation of every plan + advisor approval",
            "MESA 3 model driven by uploadable occupations, skills, training and student-survey data",
        ],
    },
    alt="Mapping of the presentation's technical stack to this prototype",
)
