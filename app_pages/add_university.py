from pathlib import Path

import pandas as pd
import streamlit as st

from core import auth
from core.curriculum import COLUMNS, clean_curriculum, delete_university, list_universities, save_university

ss = st.session_state
user = ss.user

st.title("Add a university", anchor=False)
st.caption("Upload a college's curriculum and syllabus PDFs. The app reads the semester tables and each subject's units, "
           "you check the result, and the college gets its own page under **Universities** in the menu, with the same "
           "subjects, learning roadmaps and study agents.")

if ss.get("added_uni"):
    st.success(f"Added **{ss.pop('added_uni')}**. Open it from **Universities** in the top menu.", icon=":material/check_circle:")

draft = ss.get("uni_draft")

# ---------------------------------------------------------------- step 1: upload
if draft is None:
    with st.form("uni_upload"):
        st.markdown("**1. Upload the PDFs**")
        c1, c2 = st.columns([3, 2])
        name = c1.text_input("University or college name", placeholder="e.g. National Institute of Technology Calicut")
        short = c2.text_input("Short name for the menu", placeholder="e.g. NIT Calicut", max_chars=30)
        files = st.file_uploader("Curriculum / syllabus PDFs (one PDF per branch or program)", type=["pdf"],
                                 accept_multiple_files=True)
        st.caption("Works with text-based PDFs. Scanned images can't be read.")
        go = st.form_submit_button("Read the PDFs", type="primary", icon=":material/upload_file:")
    if go:
        if not name.strip():
            st.error("Enter the university name.")
        elif not files:
            st.error("Upload at least one PDF.")
        else:
            from core.pdf_import import import_pdf

            parts = []
            with st.status("Reading the PDFs...", expanded=True) as status:
                for f in files:
                    st.write(f"Reading **{f.name}**...")
                    try:
                        df, syl, notes, program = import_pdf(f.getvalue())
                    except Exception as e:  # noqa: BLE001 - a broken or encrypted PDF
                        df, syl, notes, program = pd.DataFrame(columns=COLUMNS), {}, [f"Could not read this PDF: {e}"], ""
                    branch = program if program and len(program) <= 60 else Path(f.name).stem.replace("_", " ").replace("-", " ")[:60]
                    df["branch"] = branch
                    parts.append(dict(file=f.name, branch=branch, df=df, syl=syl, notes=notes))
                status.update(label="Done. Check the results below.", state="complete")
            ss.uni_draft = dict(name=name.strip(), short=(short or name).strip(), parts=parts)
            st.rerun()

# ---------------------------------------------------------------- step 2: review
else:
    st.markdown(f"**2. Check what was read for {draft['name']}**")
    st.caption("Fix branch names, semesters, titles or credits directly in the tables. Delete rows that aren't courses, "
               "and add missing ones at the bottom.")
    edited = []
    for i, part in enumerate(draft["parts"]):
        with st.container(border=True):
            st.markdown(f":material/picture_as_pdf: **{part['file']}**")
            for n in part["notes"]:
                st.caption(n)
            branch = st.text_input("Branch / program name", part["branch"], key=f"draft_branch_{i}", max_chars=60)
            df = part["df"].copy()
            df = df[[c for c in COLUMNS if c != "branch"]] if not df.empty else pd.DataFrame(columns=[c for c in COLUMNS if c != "branch"])
            table = st.data_editor(df, num_rows="dynamic", hide_index=True, key=f"draft_table_{i}", width="stretch",
                                   column_config={"semester": st.column_config.NumberColumn("Semester", min_value=1, max_value=12, step=1),
                                                  "code": "Code", "title": st.column_config.TextColumn("Title", width="large"),
                                                  "category": "Category", "ltp": "L-T-P", "credits": "Credits"})
            with_units = sum(1 for c in table["code"] if c in part["syl"])
            st.caption(f"{len(table)} rows · learning roadmaps for {with_units} subjects")
            table = table.assign(branch=branch.strip() or part["branch"])
            edited.append((table, part["syl"]))
    combined = clean_curriculum(pd.concat([t for t, _ in edited], ignore_index=True)) if edited else pd.DataFrame(columns=COLUMNS)
    syllabus = {k: v for _, s in edited for k, v in s.items()}
    st.markdown(f"**Total:** {combined['branch'].nunique()} branch(es) · {len(combined)} subjects · "
                f"{combined['semester'].nunique() if not combined.empty else 0} semester(s)")
    c1, c2 = st.columns(2)
    if c1.button("Save the university", type="primary", icon=":material/save:", disabled=combined.empty, width="stretch"):
        u = save_university(draft["name"], draft["short"], combined, syllabus,
                            source=", ".join(p["file"] for p in draft["parts"]), added_by=user["username"],
                            added_by_name=user["name"])
        auth.audit(user["username"], "add university", f"{u.name} ({len(combined)} subjects)")
        del ss["uni_draft"]
        ss.added_uni = u.short_name
        st.rerun()
    if c2.button("Start over", icon=":material/restart_alt:", width="stretch"):
        del ss["uni_draft"]
        st.rerun()

# ---------------------------------------------------------------- manage
uploaded = [u for u in list_universities() if not u.built_in]
if uploaded:
    st.subheader("Universities added by users", anchor=False)
    for u in uploaded:
        with st.container(border=True, horizontal=True, vertical_alignment="center"):
            st.markdown(f"**{u.short_name}** · {u.name}  \n:small[Added by {u.added_by_name or 'a user'} · from {u.source}]",
                        width="stretch")
            if user["role"] == "admin" or user["username"] == u.added_by:
                if st.button("Delete", key=f"del_uni_{u.slug}", icon=":material/delete:"):
                    if delete_university(u.slug):
                        auth.audit(user["username"], "delete university", u.name)
                        st.rerun()
    st.caption("Only the person who added a university, or an administrator, can delete it.")
