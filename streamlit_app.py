import streamlit as st

from core import auth, settings
from core.state import init

cfg = settings.load()
st.set_page_config(page_title=cfg["app_name"], page_icon=":material/route:", layout="wide")
ss = st.session_state

# Re-check the signed-in account on every run, so role changes and deletions by an
# admin take effect immediately (guests have no stored account).
if ss.get("user") and ss.user["username"] != "guest":
    fresh = auth.get_user(ss.user["username"])
    if fresh is None:
        for k in list(ss.keys()):
            del ss[k]
    else:
        ss.user = fresh
elif ss.get("user") and not cfg["allow_guest"]:
    del ss["user"]  # guest access was switched off

# Not signed in: only the login page exists.
if not ss.get("user"):
    st.navigation([st.Page("app_pages/login.py", title="Sign in", icon=":material/login:")], position="hidden").run()
    st.stop()

init()  # loads the active dataset bundle (defaults from data/*.csv) and planner state

if cfg["announcement"].strip():
    getattr(st, cfg["announcement_type"], st.info)(cfg["announcement"], icon=":material/campaign:")

user = ss.user
main = [
    st.Page("app_pages/overview.py", title="Overview", icon=":material/home:", default=True),
    st.Page("app_pages/tutorial.py", title="Tutorial", icon=":material/school:"),
    st.Page("app_pages/planner.py", title="Roadmap planner", icon=":material/route:"),
    st.Page("app_pages/simulation.py", title="Career simulation", icon=":material/hub:"),
    st.Page("app_pages/experiments.py", title="Scenario experiments", icon=":material/science:"),
    st.Page("app_pages/literature.py", title="Literature survey", icon=":material/menu_book:"),
]
if user["role"] in cfg["data_manager_roles"]:
    main.append(st.Page("app_pages/data.py", title="Data manager", icon=":material/database:"))
personal = [st.Page("app_pages/account.py", title="Account", icon=":material/account_circle:")]
if user["role"] == "admin":
    personal.insert(0, st.Page("app_pages/admin.py", title="Admin", icon=":material/admin_panel_settings:"))

page = st.navigation({"": main, user["name"]: personal}, position="top")
page.run()
