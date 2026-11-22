import pandas as pd
import streamlit as st

from core.abm import CareerPathModel, occupation_network
from core.state import data_badge
from core.viz import occupation_network_dot

ss = st.session_state
mk = ss.market


@st.cache_data(max_entries=20, show_spinner=False)
def run_simulation(params: dict, steps: int, data_key: str, _market):
    model = CareerPathModel(_market, **params)
    for _ in range(steps):
        model.step()
    df = model.datacollector.get_model_vars_dataframe()
    df.index.name = "Month"
    return df, model.occupation_table(), model.student_table()


st.title("Career simulation (MESA)", anchor=False)
st.caption(
    f"{len(mk.occupations)} occupations · {len(mk.skills)} skills · {len(mk.training)} training courses · {data_badge()}. "
    "Students with an advisor (planned careers) get a target role and targeted training; the rest apply by interest."
)

has_roadmap = ss.get("roadmap_skills") is not None and len(ss.roadmap_skills) == len(mk.skills)
has_students = bool(mk.students)
with st.form("sim"):
    use_uploaded = False
    if has_students:
        use_uploaded = st.toggle(f"Use the {len(mk.students)} uploaded students as the population", value=True)
    c1, c2, c3 = st.columns(3)
    n_students = c1.slider("Synthetic graduates", 20, 1000, 300, 10, disabled=use_uploaded)
    coverage = c1.slider("Advisor coverage (share with planned careers)", 0.0, 1.0, 0.5, 0.05,
                         help="For uploaded students, used only where the `planned` column is empty")
    months = c1.slider("Months to simulate", 6, 120, 36, 6)
    market = c2.slider("Job market size (vacancy rate)", 1.0, 40.0, 9.0, 0.5)
    min_match = c2.slider("Employer hiring bar (min skill match)", 0.3, 0.99, 0.76, 0.01)
    training = c2.slider("Training seats per provider", 0, 200, 25, 5)
    shock_on = c3.toggle("Automation shock", value=True)
    shock_month = c3.slider("Shock month", 1, 120, 12)
    shock = c3.slider("Shock intensity", 0.0, 1.0, 0.5, 0.05)
    seed = c3.number_input("Random seed", 0, 99999, 42)
    with st.expander("Advanced parameters", icon=":material/tune:"):
        a1, a2, a3 = st.columns(3)
        n_employers = a1.slider("Employers", 1, 60, 12)
        n_providers = a1.slider("Training providers", 0, 20, 4)
        learning = a2.slider("On-the-job learning rate", 0.0, 0.2, 0.02, 0.005)
        decay = a2.slider("Skill decay while unemployed", 0.0, 0.05, 0.003, 0.001, format="%.3f")
        threshold = a3.slider("Network similarity threshold", 0.5, 0.99, 0.88, 0.01)
        clones = a3.slider("Roadmap graduate clones", 1, 100, 20, disabled=not has_roadmap)
    roadmap = st.toggle(
        "Add clones of my roadmap graduate", value=has_roadmap, disabled=not has_roadmap,
        help="Generate a roadmap (and open its Career fit tab) first" if not has_roadmap else "Uses the skill vector implied by your roadmap",
    )
    st.form_submit_button("Run simulation", type="primary", icon=":material/play_arrow:")

params = dict(
    n_students=n_students, advisor_coverage=coverage, market_size=market, min_match=min_match,
    training_capacity=training, shock_step=shock_month if shock_on else None, shock_intensity=shock, rng=int(seed),
    n_employers=n_employers, n_providers=n_providers, learning_rate=learning, skill_decay=decay,
    network_threshold=threshold, use_uploaded_students=use_uploaded,
    my_student_skills=ss.roadmap_skills if (roadmap and has_roadmap) else None,
    my_student_clones=clones if (roadmap and has_roadmap) else 0,
)
with st.spinner("Running agents..."):
    df, occ_rows, stu_rows = run_simulation(params, months, ss.data_key, mk)

last = df.iloc[-1]


def pct(v):
    return "n/a" if pd.isna(v) else f"{v:.0%}"


def months_fmt(v):
    return "n/a" if pd.isna(v) else f"{v:.1f} mo"


with st.container(horizontal=True):
    st.metric("Employment rate", pct(last["Employment rate"]), border=True)
    st.metric("Planned careers", pct(last["Planned employment"]), border=True)
    st.metric("Unplanned careers", pct(last["Unplanned employment"]), border=True)
    st.metric("Time to first job (planned / unplanned)", f"{months_fmt(last['Planned time to job'])} / {months_fmt(last['Unplanned time to job'])}", border=True)
    st.metric("Skill match of employed", pct(last["Skill match (employed)"]), border=True)
    if params["my_student_clones"]:
        st.metric("Your roadmap graduates", pct(last["Roadmap employment"]), border=True)

c1, c2 = st.columns(2)
with c1.container(border=True):
    st.markdown("**Employment over time**")
    cols = [c for c in ["Planned employment", "Unplanned employment"] + (["Roadmap employment"] if params["my_student_clones"] else []) if df[c].notna().any()]
    if cols:
        st.line_chart(df[cols], y_label="Share employed", x_label="Month", alt="Employment rate over time for planned and unplanned careers")
    else:
        st.caption("No students in either group.")
with c2.container(border=True):
    st.markdown("**Labour market**")
    st.line_chart(df[["Open vacancies", "In training"]], x_label="Month", alt="Open vacancies and graduates in training over time")

st.subheader("Occupation transition network", anchor=False)
st.caption(f"Edges connect occupations whose skill requirements have cosine similarity ≥ {threshold:.2f} (del Rio-Chanona et al., 2021). Green = low, yellow = medium, red = high automation risk.")
st.graphviz_chart(occupation_network_dot(occupation_network(mk, threshold), occ_rows), width="stretch", alt="Network of occupations linked by skill similarity with worker and vacancy counts")

t1, t2, t3 = st.tabs(["Occupations", "Students", "Time series"])
with t1:
    st.dataframe(pd.DataFrame(occ_rows), hide_index=True, alt="Workers, vacancies and demand per occupation at the end of the run")
with t2:
    st.dataframe(pd.DataFrame(stu_rows), hide_index=True, alt="Final status of every simulated student")
with t3:
    st.dataframe(df, alt="All model reporters per month")
    st.download_button("Download time series CSV", df.to_csv(), "simulation.csv", "text/csv", icon=":material/download:")
