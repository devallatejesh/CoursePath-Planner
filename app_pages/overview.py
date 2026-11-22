import streamlit as st

from core import settings
from core.curriculum import branches, list_universities, load_curriculum, load_syllabus

ss = st.session_state
cfg = settings.load()
unis = list_universities()
pages = ss.get("uni_pages", {})
first_page = pages.get(unis[0].slug) if unis else None


@st.dialog(f"Welcome to {cfg['app_name']}", icon=":material/waving_hand:")
def welcome():
    st.markdown(f"Hi **{ss.user['name']}**! " + cfg["welcome_message"])
    with st.container(horizontal=True):
        if first_page and st.button(f"Open {unis[0].short_name}", type="primary", icon=":material/menu_book:"):
            st.switch_page(first_page)
        if st.button("Start the tutorial", icon=":material/school:"):
            st.switch_page("app_pages/tutorial.py")


if not ss.get("welcomed"):
    ss.welcomed = True  # show once per session
    if cfg["show_welcome"]:
        welcome()

st.title(cfg["app_name"], anchor=False)
st.caption(f"Signed in as {ss.user['name']} ({ss.user['role']})")
st.markdown(cfg["overview_intro"])

with st.container(horizontal=True):
    st.page_link("app_pages/subject_search.py", label="Search any subject's roadmap", icon=":material/search:")
    st.page_link("app_pages/tutorial.py", label="New here? Start the tutorial", icon=":material/school:")
    st.page_link("app_pages/add_university.py", label="Add your college from a PDF", icon=":material/add_circle:")
    if ss.user["role"] == "admin":
        st.page_link("app_pages/admin.py", label="Admin", icon=":material/admin_panel_settings:")

st.subheader("Universities", anchor=False)
cols = st.columns(3)
for i, u in enumerate(unis):
    df, syl = load_curriculum(u), load_syllabus(u)
    with cols[i % 3].container(border=True, height="stretch"):
        st.markdown(f"#### :material/account_balance: {u.short_name}")
        st.caption(f"{u.name} · {len(branches(df))} branch(es) · {(df['code'] != '').sum()} subjects · "
                   f"{sum(bool(syl.get(c, {}).get('units')) for c in set(df['code']))} learning roadmaps")
        if len(branches(df)) <= 6:
            st.caption(" · ".join(branches(df)))
        if u.slug in pages:
            st.page_link(pages[u.slug], label="Open", icon=":material/arrow_forward:")

st.subheader("What you get for every subject", anchor=False)
cols = st.columns(4)
features = [
    (":material/info:", "Subject details", "Course code, category, L-T-P hours and credits, straight from the curriculum."),
    (":material/route:", "Learning roadmap", "The syllabus units turned into steps, each with videos to learn that step."),
    (":material/search:", "Study resources", "NPTEL lectures, MIT OpenCourseWare, Coursera, YouTube and more, plus the textbooks."),
    (":material/smart_toy:", "Study agents", "Six agents rank subjects for your goal and build a week-by-week study plan."),
]
for col, (icon, name, text) in zip(cols, features):
    with col.container(border=True, height="stretch"):
        st.markdown(f"#### {icon} {name}")
        st.caption(text)
