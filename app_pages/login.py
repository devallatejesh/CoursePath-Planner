import time

import streamlit as st

from core import settings
from core.auth import SIGNUP_ROLES, admin_count, authenticate, create_user, reserved_admin, user_count

ss = st.session_state
cfg = settings.load()
# Without a reserved admin email, the very first account becomes the administrator.
first_account = user_count() == 0 and reserved_admin() is None
no_admin = admin_count() == 0


def advisor_code() -> str | None:
    if cfg["advisor_code"]:
        return cfg["advisor_code"]
    try:
        return st.secrets.get("advisor_code")
    except Exception:  # noqa: BLE001 - no secrets file configured
        return None


def sign_in(user: dict, *, to_admin: bool = False):
    ss.user = user
    ss.login_failures = 0
    if to_admin:
        ss.go_admin = True
    st.rerun()


def failed_attempt(message: str):
    ss.login_failures = ss.get("login_failures", 0) + 1
    if ss.login_failures >= int(cfg["max_attempts"]):
        ss.locked_until, ss.login_failures = time.time() + int(cfg["lock_seconds"]), 0
        st.rerun()
    st.error(message, icon=":material/error:")


_, mid, _ = st.columns([1, 2, 1])
with mid:
    st.title(f":material/route: {cfg['app_name']}", anchor=False)
    st.caption(cfg["tagline"])

    can_signup = cfg["allow_signup"] or no_admin  # the administrator account can always be created
    labels = [":material/login: Sign in"] + ([":material/person_add: Create account"] if can_signup else [])
    labels.append(":material/admin_panel_settings: Admin login")
    tabs = st.tabs(labels)
    locked_for = int(ss.get("locked_until", 0) - time.time())

    with tabs[0]:
        if locked_for > 0:
            st.warning(f"Too many failed attempts. Try again in {locked_for} seconds.", icon=":material/lock_clock:")
        with st.form("sign_in", border=False):
            username = st.text_input("Email", autocomplete="email", placeholder="name@example.com")
            password = st.text_input("Password", type="password", autocomplete="current-password")
            submitted = st.form_submit_button("Sign in", type="primary", icon=":material/login:", width="stretch", disabled=locked_for > 0)
        if submitted:
            user = authenticate(username, password)
            if user:
                sign_in(user)
            failed_attempt("Email or password is incorrect.")
        if first_account:
            st.info("No accounts yet. Create the first one in **Create account**; it becomes the administrator.", icon=":material/info:")

    if can_signup:
        with tabs[1]:
            if first_account:
                st.info("This first account will be the **administrator**.", icon=":material/admin_panel_settings:")
            code_required = advisor_code()
            with st.form("create", border=False):
                name = st.text_input("Your name")
                new_user = st.text_input("Email", autocomplete="email", placeholder="name@example.com")
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

    with tabs[-1]:
        st.caption("For administrators. Opens the Admin page directly after signing in.")
        if locked_for > 0:
            st.warning(f"Too many failed attempts. Try again in {locked_for} seconds.", icon=":material/lock_clock:")
        with st.form("admin_sign_in", border=False):
            a_user = st.text_input("Admin email", autocomplete="email")
            a_pass = st.text_input("Admin password", type="password", autocomplete="current-password")
            a_submit = st.form_submit_button("Sign in as admin", type="primary", icon=":material/admin_panel_settings:",
                                             width="stretch", disabled=locked_for > 0)
        if a_submit:
            user = authenticate(a_user, a_pass)
            if user and user["role"] == "admin":
                sign_in(user, to_admin=True)
            # Same message whether the password was wrong or the account isn't an admin.
            failed_attempt("Admin email or password is incorrect.")
