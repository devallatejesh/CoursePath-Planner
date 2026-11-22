import streamlit as st

from core.auth import change_password

ss = st.session_state
user = ss.user

st.title("Account", anchor=False)
with st.container(border=True):
    st.markdown(f"**{user['name']}**  \n:small[@{user['username']}] :blue-badge[{user['role']}]")
    if user["role"] == "admin":
        st.caption("Administrators can manage users, site settings and the published data on the Admin page.")
    elif user["role"] == "advisor":
        st.caption("Advisors can approve roadmaps on the planner's Validation tab.")
    else:
        st.caption("Students build and re-plan roadmaps. An advisor account is needed to approve them.")

if user["username"] != "guest":
    with st.form("change_pw"):
        st.markdown("**Change password**")
        old = st.text_input("Current password", type="password", autocomplete="current-password")
        new1 = st.text_input("New password", type="password", autocomplete="new-password")
        new2 = st.text_input("Confirm new password", type="password", autocomplete="new-password")
        if st.form_submit_button("Change password", icon=":material/key:"):
            if new1 != new2:
                st.error("The new passwords don't match.")
            else:
                ok, msg = change_password(user["username"], old, new1)
                (st.success if ok else st.error)(msg)

if st.button("Log out", type="primary", icon=":material/logout:"):
    for k in list(ss.keys()):  # clear everything, including uploaded data and plans
        del ss[k]
    st.rerun()
