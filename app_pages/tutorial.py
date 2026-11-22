import streamlit as st

from core.curriculum import list_universities

ss = st.session_state
unis = list_universities()
pages = ss.get("uni_pages", {})

st.title("Tutorial: getting started", anchor=False)
st.markdown(
    "CoursePath Planner shows every subject of your semester, with a step-by-step learning roadmap and study "
    "resources for each one, and study agents that build your weekly plan. This walkthrough takes about **4 minutes**."
)

st.header("1. Open your university", anchor=False)
st.markdown(
    "Open **Universities** in the top menu and pick your college ("
    + ", ".join(u.short_name for u in unis)
    + "). Choose your **Branch** and **Semester**. The boxes at the top show the semester's subjects, elective slots, "
    "labs and total credits."
)
if unis and unis[0].slug in pages:
    st.page_link(pages[unis[0].slug], label=f"Open {unis[0].short_name}", icon=":material/account_balance:")

st.header("2. Read a subject card", anchor=False)
st.markdown(
    "Each subject shows its **course code**, **category**, **L-T-P** hours (lecture, tutorial, practical per week), "
    "**credits** and type (theory, lab, project or elective slot).\n\n"
    "- **Study links** search the subject on NPTEL, MIT OpenCourseWare, Coursera, YouTube, Khan Academy and edX.\n"
    "- **Learning roadmap** turns each syllabus unit into a step, with videos for that step.\n"
    "- **Textbooks** lists the books named in the syllabus."
)

st.header("3. Let the study agents plan your semester", anchor=False)
st.markdown(
    "Open the **Study agents** tab, type a goal such as *AI/ML placements*, *GATE* or *core electronics*, set the "
    "weeks, your study hours per week and revision weeks, and press **Run the agents**.\n\n"
    "1. **Profile agent** reads your goal and time.\n"
    "2. **Syllabus agent** splits every unit into topics.\n"
    "3. **Priority agent** ranks subjects for your goal and explains why.\n"
    "4. **Scheduler agent** spreads the topics evenly over the weeks.\n"
    "5. **Resource agent** adds video and NPTEL links to every topic.\n"
    "6. **Review agent** checks for overloaded weeks and missing revision time.\n\n"
    "You get the agent trace, a priority table, a week-by-week plan and a CSV download."
)

st.header("4. Search any subject", anchor=False)
st.markdown(
    "Open **Subject search** in the top menu and type any subject, for example *Operating Systems*, *DSA* or *VLSI*. "
    "You don't need to pick a university. You get a step-by-step roadmap from the closest official syllabus, "
    "matched resources (W3Schools, GeeksforGeeks, Striver's A2Z sheet for DSA, YouTube, NPTEL) and a list of every "
    "university, branch and semester that teaches it."
)
st.page_link("app_pages/subject_search.py", label="Open Subject search", icon=":material/search:")

st.header("5. Add your college", anchor=False)
st.markdown(
    "Not listed? Open **Universities → Add a university**, enter the name and upload the curriculum/syllabus PDFs "
    "(one per branch). Check the table the app reads, fix anything wrong, and press **Save the university**. "
    "It then appears in the **Universities** menu for everyone."
)
st.page_link("app_pages/add_university.py", label="Add a university", icon=":material/add_circle:")

st.header("Tips and common questions", anchor=False)
faq = {
    "A subject has no roadmap": "Labs, projects and life-skills courses have no syllabus units, so they show a short note "
    "instead. Some theory subjects also have no units in the syllabus PDF.",
    "My college's PDF wasn't read well": "The reader works on text-based PDFs with a table per semester. Scanned PDFs "
    "can't be read. Fix the rows in the review table before saving, or add missing ones at the bottom.",
    "What do I take in an elective slot?": "Pick one course from your department's elective list. Your faculty advisor "
    "can tell you which basket fits your goals.",
    "Is this the latest curriculum?": "It comes from the PDFs the university was added from. Check with your department "
    "for changes.",
    "I forgot my password": "Accounts are stored on the computer running the app (`auth/users.json`). Ask whoever runs it to "
    "remove your entry so you can create the account again.",
}
for q, a in faq.items():
    with st.expander(q, icon=":material/help:"):
        st.markdown(a)
