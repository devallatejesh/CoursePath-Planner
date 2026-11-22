import time

import streamlit as st

from core import settings
from core.auth import SIGNUP_ROLES, authenticate, create_user, user_count

ss = st.session_state
cfg = settings.load()
first_account = user_count() == 0


def advisor_code() -> str | None:
    if cfg["advisor_code"]:
        return cfg["advisor_code"]
    try:
        return st.secrets.get("advisor_code")
    except Exception:  # noqa: BLE001 - no secrets file configured
        return None


def sign_in(user: dict):
    ss.user = user
    ss.login_failures = 0
    st.rerun()


_, mid, _ = st.columns([1, 2, 1])
with mid:
    st.title(f":material/route: {cfg['app_name']}", anchor=False)
    st.caption(cfg["tagline"])

    can_signup = cfg["allow_signup"] or first_account  # the first (admin) account can always be created
    tabs = st.tabs([":material/login: Sign in"] + ([":material/person_add: Create account"] if can_signup else []))

    with tabs[0]:
        locked_for = int(ss.get("locked_until", 0) - time.time())
        if locked_for > 0:
            st.warning(f"Too many failed attempts. Try again in {locked_for} seconds.", icon=":material/lock_clock:")
        with st.form("sign_in", border=False):
            username = st.text_input("Username", autocomplete="username")
            password = st.text_input("Password", type="password", autocomplete="current-password")
            submitted = st.form_submit_button("Sign in", type="primary", icon=":material/login:", width="stretch", disabled=locked_for > 0)
        if submitted:
            user = authenticate(username, password)
            if user:
                sign_in(user)
            ss.login_failures = ss.get("login_failures", 0) + 1
            if ss.login_failures >= int(cfg["max_attempts"]):
                ss.locked_until, ss.login_failures = time.time() + int(cfg["lock_seconds"]), 0
                st.rerun()
            st.error("Username or password is incorrect.", icon=":material/error:")
        if first_account:
            st.info("No accounts yet. Create the first one in **Create account**; it becomes the administrator.", icon=":material/info:")

    if can_signup:
        with tabs[1]:
            if first_account:
                st.info("This first account will be the **administrator**.", icon=":material/admin_panel_settings:")
            code_required = advisor_code()
            with st.form("create", border=False):
                name = st.text_input("Your name")
                new_user = st.text_input("Username", help="3-32 characters: lowercase letters, numbers, dot, dash or underscore",
                                         autocomplete="username")
                pw1 = st.text_input("Password", type="password", help="At least 8 characters with a letter and a number",
                                    autocomplete="new-password")
                pw2 = st.text_input("Confirm password", type="password", autocomplete="new-password")
                role = st.segmented_control("I am a", SIGNUP_ROLES, default="student", required=True, format_func=str.capitalize,
                                            disabled=first_account)
                code = st.text_input("Advisor code", type="password",
                                     help="Ask your administrator. Only needed for advisor accounts.") if code_required and not first_account else ""
                created = st.form_submit_button("Create account", type="primary", icon=":material/person_add:", width="stretch")
            if created:
                if pw1 != pw2:
                    st.error("The passwords don't match.")
                elif role == "advisor" and code_required and not first_account and code != code_required:
                    st.error("The advisor code is not correct.")
                else:
                    ok, msg = create_user(new_user, pw1, name, role)
                    if ok:
                        sign_in(authenticate(new_user, pw1))
                    st.error(msg)
            if not code_required and not first_account:
                st.caption("Anyone can create an advisor account. An admin can require an invite code on the Admin page.")

    if cfg["allow_guest"]:
        st.divider()
        if st.button("Continue as guest", icon=":material/person:", width="stretch",
                     help="Explore everything as a student. Nothing is saved to an account."):
            sign_in({"username": "guest", "name": "Guest", "role": "student"})
