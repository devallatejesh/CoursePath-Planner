import os

import streamlit as st

from core import auth, settings
from core.curriculum import list_universities

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
# admin take effect immediately. A session without a stored account is signed out.
if ss.get("user"):
    fresh = auth.get_user(ss.user["username"])
    if fresh is None:
        for k in list(ss.keys()):
            del ss[k]
    else:
        ss.user = fresh

# Not signed in: only the login page exists.
if not ss.get("user"):
    st.navigation([st.Page("app_pages/login.py", title="Sign in", icon=":material/login:")], position="hidden").run()
    st.stop()

if cfg["announcement"].strip():
    getattr(st, cfg["announcement_type"], st.info)(cfg["announcement"], icon=":material/campaign:")

user = ss.user
is_admin = user["role"] == "admin"
land_on_admin = is_admin and ss.pop("go_admin", False)  # signed in through "Admin login"

main = [st.Page("app_pages/overview.py", title="Overview", icon=":material/home:", default=not land_on_admin)]
if is_admin:  # second in the menu so it is always visible, never hidden under "more"
    main.append(st.Page("app_pages/admin.py", title="Admin", icon=":material/admin_panel_settings:", default=land_on_admin))
main.append(st.Page("app_pages/subject_search.py", title="Subject search", icon=":material/search:"))
main.append(st.Page("app_pages/tutorial.py", title="Tutorial", icon=":material/school:"))

# One page per university (built-in first, then ones users added), all served by app_pages/semester.py.
unis = list_universities()
uni_pages = {}
for u in unis:
    uni_pages[u.slug] = st.Page("app_pages/semester.py", title=u.short_name, url_path=f"uni-{u.slug}",
                                icon=":material/account_balance:" if u.built_in else ":material/school:")
universities = list(uni_pages.values()) + [
    st.Page("app_pages/add_university.py", title="Add a university", icon=":material/add_circle:")
]
ss.uni_pages = uni_pages
personal = [st.Page("app_pages/account.py", title="Account", icon=":material/account_circle:")]

page = st.navigation({"": main, "Universities": universities, user["name"]: personal}, position="top")
ss.current_uni = next((slug for slug, p in uni_pages.items() if p.url_path == page.url_path), ss.get("current_uni"))
if land_on_admin:
    ss.welcomed = True  # skip the welcome pop-up for admin sign-ins
page.run()
