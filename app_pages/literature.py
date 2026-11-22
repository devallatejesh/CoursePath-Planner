import pandas as pd
import streamlit as st

ss = st.session_state

st.title("Literature survey", anchor=False)
st.caption("Agent-based models of careers and labour markets. Edit or replace this table in the Data manager.")

lit = ss.frames.get("literature", pd.DataFrame())
if lit.empty:
    st.info("No literature dataset loaded.", icon=":material/info:")
else:
    pretty = lit.rename(columns=lambda c: c.replace("_", " ").capitalize())
    st.dataframe(pretty, hide_index=True, alt="Surveyed agent-based modelling studies")

st.subheader("Agents built in the MESA model", anchor=False)
st.table(
    pd.DataFrame(
        [
            ("Student / job seeker", "Skill vector, interests, goal; trains, applies, gets hired", "`StudentAgent`"),
            ("Job / occupation", "Required skills, salary, demand multiplier, automation risk", "`OccupationAgent`"),
            ("Employer", "Opens vacancies (Poisson), hires the best match above a bar, lays off after shocks", "`EmployerAgent`"),
            ("Training provider", "Courses that raise specific skills, with capacity and efficiency", "`TrainingProviderAgent`"),
            ("Advisor / mentor", "Picks the next best role (match, interest, demand) and the gap-closing course", "`AdvisorAgent`"),
        ],
        columns=["Agent", "Behaviour", "Class in core/abm.py"],
    ),
    alt="Agents from the deck mapped to classes in the code",
)

st.subheader("Where to get real data", anchor=False)
st.markdown(
    """
- **Occupations and skills** (`occupations.csv`): O*NET skills and work activities
- **Demand and wages:** BLS Occupational Outlook, India PLFS (MoSPI), Kaggle job-posting datasets
- **Training** (`training.csv`): institution course lists, National Career Service (ncs.gov.in), Skill India / NSQF
- **Students** (`students.csv`): Google Forms survey or Holland-code interest tests
- **Catalog, requirements and seats** (`courses.csv`, `requirements.csv`, `seats.csv`): your university's catalog, degree audit and registrar exports
"""
)
from core import settings  # noqa: E402

if ss.user["role"] in settings.load()["data_manager_roles"]:
    st.page_link("app_pages/data.py", label="Upload your data", icon=":material/database:")
