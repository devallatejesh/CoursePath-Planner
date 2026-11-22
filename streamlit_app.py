import os

import streamlit as st

from core import auth, settings
from core.state import init

# Root-level secrets (.streamlit/secrets.toml locally, "Secrets" on Streamlit Cloud)
# become environment variables, which core/auth.py reads.
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, (str, int, float)) and _k not in os.environ:
            os.environ[_k] = str(_v)
except Exception:  # noqa: BLE001 - no secrets configured
    pass
auth.ensure_seeded_admin()  # recreate the built-in administrator if it is missing

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
is_admin = user["role"] == "admin"
land_on_admin = is_admin and ss.pop("go_admin", False)  # signed in through "Admin login"

main = [st.Page("app_pages/overview.py", title="Overview", icon=":material/home:", default=not land_on_admin)]
if is_admin:  # second in the menu so it is always visible, never hidden under "more"
    main.append(st.Page("app_pages/admin.py", title="Admin", icon=":material/admin_panel_settings:", default=land_on_admin))
main += [
    st.Page("app_pages/tutorial.py", title="Tutorial", icon=":material/school:"),
    st.Page("app_pages/planner.py", title="Roadmap planner", icon=":material/route:"),
    st.Page("app_pages/simulation.py", title="Career simulation", icon=":material/hub:"),
    st.Page("app_pages/experiments.py", title="Scenario experiments", icon=":material/science:"),
    st.Page("app_pages/literature.py", title="Literature survey", icon=":material/menu_book:"),
]
if user["role"] in cfg["data_manager_roles"]:
    main.append(st.Page("app_pages/data.py", title="Data manager", icon=":material/database:"))
personal = [st.Page("app_pages/account.py", title="Account", icon=":material/account_circle:")]

page = st.navigation({"": main, user["name"]: personal}, position="top")
if land_on_admin:
    ss.welcomed = True  # skip the welcome pop-up for admin sign-ins
page.run()
