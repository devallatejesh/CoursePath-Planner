import pandas as pd
import streamlit as st

from core import auth, settings

ss = st.session_state
me = ss.get("user") or {}

# Defence in depth: the page is only in the menu for admins, but check again here.
if me.get("role") != "admin" or not auth.get_user(me.get("username", "")) or auth.get_user(me["username"])["role"] != "admin":
    st.error("This page is only for administrators.", icon=":material/lock:")
    st.stop()

ss.setdefault("users_ver", 0)
st.title("Admin", anchor=False)
st.caption("Manage accounts and site settings. Every change here is recorded in the audit log.")

tab_users, tab_settings, tab_audit = st.tabs(
    [":material/group: Users", ":material/tune: Site settings", ":material/history: Audit log"]
)

# ========================================================================= users
with tab_users:
    users = auth.list_users()
    with st.container(horizontal=True):
        st.metric("Users", len(users), border=True)
        for role in auth.ROLES:
            st.metric(role.capitalize() + "s", sum(u["role"] == role for u in users), border=True)

    st.markdown("**Edit names and roles**")
    base = pd.DataFrame(users, columns=["username", "name", "role", "created", "last_login"])
    edited = st.data_editor(
        base,
        key=f"users_ed_{ss.users_ver}",
        hide_index=True,
        disabled=["username", "created", "last_login"],
        column_config={
            "username": "Email",
            "name": st.column_config.TextColumn("Name", max_chars=60, required=True),
            "role": st.column_config.SelectboxColumn("Role", options=list(auth.ROLES), required=True),
            "created": "Created (UTC)",
            "last_login": "Last sign-in (UTC)",
        },
        alt="All user accounts with editable names and roles",
    )
    changes = [(r.username, r.name, r.role) for r, b in zip(edited.itertuples(), base.itertuples()) if (r.name, r.role) != (b.name, b.role)]
    if st.button(f"Save {len(changes)} change(s)", type="primary", icon=":material/save:", disabled=not changes):
        msgs = [auth.update_user(u, name=n, role=r, by=me["username"]) for u, n, r in changes]
        for ok, msg in msgs:
            (st.toast if ok else st.error)(msg)
        ss.users_ver += 1
        st.rerun()

    c1, c2 = st.columns(2)
    with c1.container(border=True):
        st.markdown("**Create a user**")
        with st.form("admin_create", clear_on_submit=True, border=False):
            name = st.text_input("Name")
            username = st.text_input("Email")
            role = st.selectbox("Role", auth.ROLES, format_func=str.capitalize)
            pw = st.text_input("Password", type="password", help="At least 8 characters with a letter and a number")
            if st.form_submit_button("Create user", icon=":material/person_add:"):
                ok, msg = auth.create_user(username, pw, name, role, by=me["username"])
                if ok:
                    ss.users_ver += 1
                    st.toast(msg, icon=":material/check_circle:")
                    st.rerun()
                else:
                    st.error(msg)

    others = [u["username"] for u in users]
    with c2.container(border=True):
        st.markdown("**Reset a password**")
        target = st.selectbox("User", others, key="reset_user", index=None, placeholder="Choose a user")
        if st.button("Generate a temporary password", icon=":material/key:", disabled=target is None):
            temp = auth.temporary_password()
            ok, msg = auth.reset_password(target, temp, by=me["username"])
            if ok:
                ss.last_temp = (target, temp)
            else:
                st.error(msg)
        if ss.get("last_temp") and ss.last_temp[0] == target:
            st.success(f"New password for **{target}**. Share it privately; it won't be shown again.", icon=":material/key:")
            st.code(ss.last_temp[1], language=None)
            if st.button("I've copied it", key="clear_temp"):
                ss.pop("last_temp")
                st.rerun()

    with st.container(border=True):
        st.markdown("**Delete a user**")
        deletable = [u for u in others if u != me["username"]]
        victim = st.selectbox("User to delete", deletable, index=None, placeholder="Choose a user", key="del_user")
        sure = st.checkbox("I understand this permanently deletes the account", key="del_sure")
        if st.button("Delete user", icon=":material/delete:", disabled=not (victim and sure)):
            ok, msg = auth.delete_user(victim, by=me["username"])
            (st.toast if ok else st.error)(msg)
            if ok:
                ss.users_ver += 1
                ss.pop("del_sure", None)
                st.rerun()
        st.caption("You can't delete yourself or the last administrator.")

# ====================================================================== settings
with tab_settings:
    cur = settings.load()
    with st.form("site_settings"):
        st.markdown("**Branding and text**")
        app_name = st.text_input("App name", cur["app_name"], max_chars=60)
        tagline = st.text_input("Sign-in page tagline", cur["tagline"], max_chars=200)
        overview_intro = st.text_area("Overview introduction", cur["overview_intro"], height=100)
        welcome_message = st.text_area("Welcome pop-up message (Markdown)", cur["welcome_message"], height=150)
        show_welcome = st.toggle("Show the welcome pop-up after sign-in", cur["show_welcome"])

        st.markdown("**Announcement banner** (shown at the top of every page; leave empty to hide)")
        b1, b2 = st.columns([3, 1])
        announcement = b1.text_input("Banner text", cur["announcement"], max_chars=300)
        announcement_type = b2.selectbox("Style", settings.ANNOUNCEMENT_TYPES,
                                         index=settings.ANNOUNCEMENT_TYPES.index(cur["announcement_type"]))

        st.markdown("**Access**")
        allow_signup = st.toggle("Allow people to create accounts", cur["allow_signup"])
        advisor_code = st.text_input("Advisor invite code", cur["advisor_code"], type="password",
                                     help="If set, creating an advisor account needs this code. Leave empty to let anyone choose Advisor.")
        l1, l2 = st.columns(2)
        max_attempts = l1.number_input("Failed sign-ins before lockout", 1, 50, int(cur["max_attempts"]))
        lock_seconds = l2.number_input("Lockout length (seconds)", 0, 3600, int(cur["lock_seconds"]))
        saved = st.form_submit_button("Save settings", type="primary", icon=":material/save:")
    if saved:
        ok, msg = settings.save(dict(
            app_name=app_name.strip(), tagline=tagline.strip(), overview_intro=overview_intro, welcome_message=welcome_message,
            show_welcome=show_welcome, announcement=announcement.strip(), announcement_type=announcement_type,
            allow_signup=allow_signup, advisor_code=advisor_code.strip(),
            max_attempts=int(max_attempts), lock_seconds=int(lock_seconds),
        ), by=me["username"])
        if ok:
            st.toast(msg, icon=":material/check_circle:")
            st.rerun()
        st.error(msg)
    with st.expander("Reset all settings to defaults", icon=":material/restart_alt:"):
        if st.checkbox("I want to reset every setting", key="reset_sure") and st.button("Reset settings"):
            settings.reset(by=me["username"])
            st.rerun()

# ========================================================================= audit
with tab_audit:
    log = auth.read_audit()
    if not log:
        st.caption("No admin actions yet.")
    else:
        df = pd.DataFrame(log, columns=["time", "user", "action", "detail"])
        actions = sorted(df["action"].unique())
        chosen = st.multiselect("Filter by action", actions, placeholder="All actions")
        if chosen:
            df = df[df["action"].isin(chosen)]
        st.dataframe(df, hide_index=True, alt="Recent admin and account actions, newest first")
        st.download_button("Download audit log", df.to_csv(index=False), "audit_log.csv", "text/csv", icon=":material/download:")
