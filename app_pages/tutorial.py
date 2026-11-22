import streamlit as st

from core import settings
from core.datasets import DATA_DIR, SPECS

ss = st.session_state
cat, mk = ss.catalog, ss.market
can_edit_data = ss.user["role"] in settings.load()["data_manager_roles"]
careers = list(cat.careers.values())
per_year = len(cat.requirements.seasons)


def try_goal(text: str, key: str):
    """Button that pre-fills the planner with an example goal and opens it."""
    if st.button("Try this", key=key, icon=":material/play_arrow:"):
        ss.goal_text = text
        ss.goal_career = "Infer from my text"
        ss.tutorial_prefilled = True
        st.switch_page("app_pages/planner.py")


st.title("Tutorial: getting started", anchor=False)
st.markdown(
    "CoursePath Planner builds a term-by-term degree roadmap with four cooperating AI agents, keeps it up to date when "
    "things change, links study resources to every subject, and simulates how students fare in the job market. "
    "This walkthrough takes about **10 minutes**. Each step has a button that takes you to the right page."
)

with st.container(border=True):
    st.markdown("**The app at a glance**")
    st.table(
        {
            "Page": ["Overview", "Roadmap planner", "Career simulation", "Scenario experiments", "Literature survey", "Data manager"],
            "Use it to": [
                "See how the agents work together and what data is loaded",
                "Turn your goals into a validated term-by-term plan, with study links per subject",
                "Watch simulated graduates search for jobs (planned vs unplanned careers)",
                "Compare many simulation runs while changing two settings",
                "Read the research the model is based on",
                "Upload or edit your own courses, rules, careers, jobs and resources",
            ],
        },
        alt="What each page of the app is for",
    )
    st.caption("Pages that don't fit in the top menu are under **more**. Your **Account** page (log out, change password) is there too.")

# ------------------------------------------------------------------- step 0
st.header("0. Your account", anchor=False)
st.markdown(
    f"You're signed in as **{ss.user['name']}** with the **{ss.user['role']}** role.\n"
    "- **Students** build, re-plan and explore roadmaps.\n"
    "- **Advisors** can also press **Approve as advisor** once a roadmap passes every check.\n\n"
    "Change your password or **Log out** on the **Account** page (top menu, under your name). "
    "Logging out clears your plans and any uploaded data from this browser session."
)

# ------------------------------------------------------------------- step 1
st.header("1. Build your first roadmap", anchor=False)
st.markdown(
    "Open **Roadmap planner** and describe what you want in plain English. The **Goal agent** picks out:\n"
    "- **a career goal** (or choose one from the *Career goal* list),\n"
    f"- **a timeline** such as *4 years* or *7 semesters* (one year = {per_year} terms here: {', '.join(cat.requirements.seasons)}),\n"
    "- **workload words** like *part-time* (max 12 credits) or *avoid hard courses*,\n"
    "- **interests** such as " + ", ".join(f"`{t}`" for t in cat.interest_tags[:6]) + ".\n\n"
    "Add courses you've already passed under *Already completed*, then press **Generate roadmap**."
)
examples = []
if careers:
    examples.append(f"I want to become a {careers[0].name.lower()} and graduate in 4 years.")
if len(careers) > 1:
    examples.append(f"I'd like to work as a {careers[1].name.lower()}. I study part-time and want to avoid hard courses.")
if len(careers) > 2:
    tag = cat.interest_tags[0] if cat.interest_tags else "my field"
    examples.append(f"Career goal: {careers[2].name.lower()}. I'm interested in {tag} and want to graduate early.")
for i, ex in enumerate(examples):
    with st.container(border=True, horizontal=True, vertical_alignment="center"):
        st.markdown(f"*“{ex}”*", width="stretch")
        try_goal(ex, f"ex_{i}")

# ------------------------------------------------------------------- step 2
st.header("2. Read the result", anchor=False)
c1, c2 = st.columns(2)
with c1.container(border=True, height="stretch"):
    st.markdown(
        "**Summary cards** show the projected graduation term, number of terms, credits and whether the "
        "**guardrails** passed.\n\n"
        "**Agent trace** shows what each agent did:\n"
        "1. *Goal agent*: what it understood from your text\n"
        "2. *Constraint agent*: prerequisites, seasons, seats and credit limits\n"
        "3. *Planning agent*: which courses it chose and why\n"
        "4. *Guardrails*: an independent re-check of every rule"
    )
with c2.container(border=True, height="stretch"):
    st.markdown(
        "**Roadmap cards** list each term's subjects. Badges show the category, and a red **hard** badge marks "
        "courses with a low historical pass rate.\n\n"
        "**Tabs below the roadmap:**\n"
        "- *Prerequisite graph*: which course unlocks which\n"
        "- *Course table*: the reason each course was chosen, plus a CSV download\n"
        "- *Validation*: errors and warnings, and the **Approve as advisor** button\n"
        "- *Career fit*: which jobs your planned courses prepare you for"
    )

# ------------------------------------------------------------------- step 3
st.header("3. Use the study resources", anchor=False)
st.markdown(
    "Under every subject you'll find study links:\n"
    "- :material/menu_book: a **reading** link chosen for that course (by default a Wikipedia overview),\n"
    ":material/search: plus one-click searches for the course on "
    + (", ".join(n for n, _, _ in cat.resource_links) or "your configured learning sites") + ".\n\n"
    "The **Study resources** tab lists them all term by term. Use the switch *Show study resources under each subject* "
    "to hide them when you only want the plan. You can add your own links (lecture notes, textbook chapters) in the **Data manager**."
)

# ------------------------------------------------------------------- step 4
st.header("4. Something changed? Re-plan", anchor=False)
st.markdown(
    "At the bottom of the planner, under **Something changed?**, pick what happened and press **Re-plan**. "
    "The **Adaptation agent** keeps finished terms as history and rebuilds the rest."
)
st.table(
    {
        "Event": ["Dropped / failed a course", "Section is full", "Course cancelled", "Goal changed"],
        "What the agent does": [
            "Keeps that term as history without the course, then schedules a retake and moves the courses that depend on it",
            "Marks the section full for that term and finds another term or option",
            "Removes the course for good and picks a substitute elective",
            "Re-chooses electives for the new career from that term onward",
        ],
    },
    alt="Re-plan events and what the Adaptation agent does for each",
)
st.markdown(
    "A **What changed** table lists moved, added and removed courses, and *Plan versions* keeps the history. "
    "If the guardrails pass, press **Approve as advisor** on the *Validation* tab."
)
st.page_link("app_pages/planner.py", label="Open the Roadmap planner", icon=":material/route:")

# ------------------------------------------------------------------- step 5
st.header("5. Test careers in the job-market simulation", anchor=False)
st.markdown(
    f"**Career simulation** runs an agent-based (MESA) model with {len(mk.occupations)} occupations and "
    f"{len(mk.skills)} skills. Simulated graduates look for jobs every month. Those with an **advisor** "
    "(*planned careers*) get a target role and targeted training; the rest apply by interest (*unplanned*).\n\n"
    "Things to try:\n"
    "1. Press **Run simulation** with the defaults and compare the *Planned* and *Unplanned* employment lines.\n"
    "2. Turn the **Automation shock** off and on and watch high-risk jobs (red in the network) shrink.\n"
    "3. After building a roadmap (step 1), switch on **Add clones of my roadmap graduate** to see how someone with "
    "your planned courses would do.\n\n"
    "**Scenario experiments** repeats the simulation many times. Pick two settings (for example *Advisor coverage* "
    "and *Automation shock intensity*), choose their values and press **Run experiments**."
)
with st.container(horizontal=True):
    st.page_link("app_pages/simulation.py", label="Open Career simulation", icon=":material/hub:")
    st.page_link("app_pages/experiments.py", label="Open Scenario experiments", icon=":material/science:")

# ------------------------------------------------------------------- step 6
st.header("6. Use your own data", anchor=False)
st.markdown(
    "Everything comes from tables you can replace on the **Data manager** page:\n"
    "1. Choose a dataset, then press **Template** to download an example of the format.\n"
    "2. Fill it in with Excel or Google Sheets and upload it (CSV, Excel or JSON). You can also edit rows directly in the table.\n"
    "3. Check the **Validation** box. Errors (such as an unknown prerequisite) must be fixed; warnings are advice.\n"
    "4. Press **Apply to the whole app**. **Reset to defaults** brings back the demo data.\n\n"
    "To replace several tables at once, upload a **ZIP** of CSV files named after the datasets."
)
with st.expander("Which datasets are there?", icon=":material/dataset:"):
    st.table(
        {
            "Dataset (file name)": [f"{v.title} ({k}.csv)" for k, v in SPECS.items()],
            "Needed?": ["Optional" if v.optional_dataset or k == "literature" else "Required" for k, v in SPECS.items()],
            "Required columns": [", ".join(v.required) or "any" for v in SPECS.values()],
        },
        alt="All datasets with their file names and required columns",
    )
sample = DATA_DIR / "samples" / "biology_example.zip"
with st.container(horizontal=True, vertical_alignment="center"):
    if sample.exists():
        st.download_button("Download a sample program (biology ZIP)", sample.read_bytes(), "biology_example.zip",
                           "application/zip", icon=":material/download:")
    if can_edit_data:
        st.page_link("app_pages/data.py", label="Open the Data manager", icon=":material/database:")
    else:
        st.caption("Your administrator has limited data editing to some roles.")
st.caption("Uploaded data lasts for your browser session. Download the bundle on the Data manager to keep it.")

# ------------------------------------------------------------------- FAQ
st.header("Tips and common questions", anchor=False)
faq = {
    "My graduation says *Not reachable*": "Open the *Validation* tab. Usually the credit limit is too low for two courses "
    "that must be taken together, or there aren't enough electives for the chosen career. Raise *Max credits per term* or pick another career goal.",
    "The career I typed wasn't detected": "Pick it from the *Career goal* list instead. Detection uses each career's "
    "`keywords` column, which you can extend in the Data manager.",
    "Why is my plan longer than my target?": "Prerequisite chains and courses that only run in one season set a minimum. "
    "The Constraint agent reports that minimum in the agent trace. Turn off *Balance load* to pack courses for the earliest finish.",
    "My uploaded data disappeared": "Reloading the page or typing a page address starts a new session (you'll need to "
    "sign in again). Move between pages with the top menu, and download your bundle on the Data manager to keep it.",
    "I can't press Approve as advisor": "Approval needs an advisor account and a roadmap with no errors. Students see a note instead of the button.",
    "I forgot my password": "Accounts are stored on the computer running the app (`auth/users.json`). Ask whoever runs it to "
    "remove your entry so you can create the account again.",
    "Are the numbers real?": "No. The demo catalog and job market are synthetic. Upload institutional, O*NET or BLS data "
    "to make the results meaningful.",
    "The first page load is slow": "The simulation library loads once, which takes about 10 seconds. After that it's fast.",
}
for q, a in faq.items():
    with st.expander(q, icon=":material/help:"):
        st.markdown(a)
