import streamlit as st

from core.auth import change_password

ss = st.session_state
user = ss.user

st.title("Account", anchor=False)
with st.container(border=True):
    st.markdown(f"**{user['name']}**  \n:small[{user['username']}] :blue-badge[{user['role']}]")
    if user["role"] == "admin":
        st.caption("Administrators can manage users and site settings on the Admin page.")
    else:
        st.caption("Open your college under **Universities** in the menu to see your subjects, learning roadmaps and study agents.")

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
    for k in list(ss.keys()):  # clear the whole browser session
        del ss[k]
    st.rerun()
