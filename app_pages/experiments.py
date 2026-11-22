import altair as alt
import mesa
import pandas as pd
import streamlit as st

from core.abm import CareerPathModel
from core.state import data_badge

ss = st.session_state
mk = ss.market

# Parameters that can be swept, with their value grid and display format.
SWEEPABLE = {
    "advisor_coverage": ("Advisor coverage", [0.0, 0.25, 0.5, 0.75, 1.0], "{:.0%}"),
    "shock_intensity": ("Automation shock intensity", [0.0, 0.3, 0.6, 0.9], "{:.0%}"),
    "min_match": ("Employer hiring bar", [0.6, 0.7, 0.76, 0.85], "{:.2f}"),
    "market_size": ("Job market size", [5.0, 9.0, 15.0, 25.0], "{:g}"),
    "training_capacity": ("Training seats per provider", [0, 10, 25, 60], "{:d}"),
    "n_employers": ("Employers", [4, 12, 30], "{:d}"),
    "skill_decay": ("Skill decay", [0.0, 0.003, 0.01], "{:.3f}"),
}
METRICS = ["Employment rate", "Planned employment", "Unplanned employment", "Skill match (employed)",
           "Planned time to job", "Unplanned time to job", "Avg salary (k)", "Open vacancies"]


@st.cache_data(max_entries=10, show_spinner=False)
def run_batch(params_key: tuple, seeds: int, months: int, data_key: str, _market) -> pd.DataFrame:
    params = {k: (list(v) if isinstance(v, tuple) else v) for k, v in params_key}
    results = mesa.batch_run(
        CareerPathModel, parameters={"market": _market, **params}, rng=list(range(1, seeds + 1)),
        max_steps=months, number_processes=1, data_collection_period=-1, display_progress=False,
    )
    return pd.DataFrame(results).drop(columns=["market"], errors="ignore")


st.title("Scenario experiments", anchor=False)
st.caption(f"Sweep any two model parameters with MESA `batch_run` and several random seeds per scenario · {data_badge()}")

keys = list(SWEEPABLE)
# Parameter pickers live outside the form so their value grids update immediately.
c1, c2 = st.columns(2)
x_param = c1.selectbox("Sweep (x-axis)", keys, format_func=lambda k: SWEEPABLE[k][0])
s_param = c2.selectbox("Compare by (colour)", [k for k in keys if k != x_param], format_func=lambda k: SWEEPABLE[k][0])
with st.form("batch"):
    c1, c2 = st.columns(2)
    x_grid, s_grid = SWEEPABLE[x_param][1], SWEEPABLE[s_param][1]
    x_vals = c1.pills(f"{SWEEPABLE[x_param][0]} values", x_grid, selection_mode="multi", default=x_grid[::2] or x_grid,
                      format_func=lambda v, f=SWEEPABLE[x_param][2]: f.format(v), key=f"xv_{x_param}")
    s_vals = c2.pills(f"{SWEEPABLE[s_param][0]} values", s_grid, selection_mode="multi", default=s_grid[:2],
                      format_func=lambda v, f=SWEEPABLE[s_param][2]: f.format(v), key=f"sv_{s_param}")
    d1, d2, d3, d4 = st.columns(4)
    seeds = d1.slider("Seeds per scenario", 1, 10, 3)
    months = d2.slider("Months", 6, 72, 24, 6)
    n_students = d3.slider("Graduates per run", 50, 600, 200, 50)
    metric = d4.selectbox("Metric to chart", METRICS)
    go = st.form_submit_button("Run experiments", type="primary", icon=":material/science:")

if not x_vals or not s_vals:
    st.warning("Pick at least one value for each parameter.")
    st.stop()

runs = len(x_vals) * len(s_vals) * seeds
if not go and "batch_ran" not in ss:
    st.info(f"This will run {runs} simulations. Press **Run experiments**.", icon=":material/info:")
    st.stop()
ss.batch_ran = True

params_key = ((x_param, tuple(sorted(x_vals))), (s_param, tuple(sorted(s_vals))), ("n_students", n_students))
with st.spinner(f"Running {runs} simulations..."):
    df = run_batch(params_key, seeds, months, ss.data_key, mk)

x_label, _, x_fmt = SWEEPABLE[x_param]
s_label, _, s_fmt = SWEEPABLE[s_param]
summary = df.groupby([x_param, s_param])[METRICS].mean().reset_index()
summary[x_label] = summary[x_param].map(lambda v: x_fmt.format(type(SWEEPABLE[x_param][1][0])(v)))
summary[s_label] = summary[s_param].map(lambda v: s_fmt.format(type(SWEEPABLE[s_param][1][0])(v)))
is_share = metric in ("Employment rate", "Planned employment", "Unplanned employment", "Skill match (employed)")

with st.container(border=True):
    st.markdown(f"**{metric} after {months} months**")
    chart = alt.Chart(summary).mark_bar().encode(
        x=alt.X(f"{x_label}:N", sort=None),
        xOffset=f"{s_label}:N",
        y=alt.Y(f"{metric}:Q", axis=alt.Axis(format="%" if is_share else ""), scale=alt.Scale(zero=False)),
        color=alt.Color(f"{s_label}:N"),
        tooltip=[x_label, s_label, alt.Tooltip(f"{metric}:Q", format=".1%" if is_share else ".2f")],
    )
    st.altair_chart(chart, alt=f"{metric} by {x_label} and {s_label}")

st.dataframe(summary[[x_label, s_label] + METRICS], hide_index=True, alt="Mean outcome per scenario across seeds")
st.caption(f"{len(df)} runs · means across {seeds} seed(s).")
st.download_button("Download raw runs CSV", df.to_csv(index=False), "batch_runs.csv", "text/csv", icon=":material/download:")
