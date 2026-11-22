import pandas as pd
import streamlit as st

from core.datasets import SPECS, bundle_to_zip, frames_from_zip, has_errors, read_table, sample_frame, validate
from core.state import activate, data_badge, default_frames

ss = st.session_state
from core import settings  # noqa: E402

if ss.user["role"] not in settings.load()["data_manager_roles"]:
    st.error("Your administrator has not given your role access to the Data manager.", icon=":material/lock:")
    st.stop()

# Draft = what the user is editing; it only becomes active after "Apply".
# ``base`` is what the table editor starts from (it never changes while the user edits,
# otherwise Streamlit would re-apply the same row edits on every rerun); ``draft`` is the
# editor's current output.
if "draft" not in ss or "base" not in ss:
    ss.base = {k: v.copy() for k, v in ss.frames.items()}
    ss.draft = {k: v.copy() for k, v in ss.frames.items()}
    ss.draft_ver = {k: 0 for k in SPECS}
    ss.seen_uploads = set()
for k in SPECS:  # datasets added after the draft was created
    ss.base.setdefault(k, ss.frames.get(k, pd.DataFrame()).copy())
    ss.draft.setdefault(k, ss.base[k].copy())
    ss.draft_ver.setdefault(k, 0)


def set_draft(name: str, df: pd.DataFrame):
    ss.base[name] = df
    ss.draft[name] = df.copy()
    ss.draft_ver[name] = ss.draft_ver.get(name, 0) + 1


st.title("Data manager", anchor=False)
st.markdown(
    f"Every page runs on these tables. Upload your own files (CSV, Excel or JSON), edit rows in place, "
    f"then **Apply** to validate and switch the whole app to your data. Currently using {data_badge()}."
)

# ------------------------------------------------------------ whole-bundle actions
with st.container(border=True):
    st.markdown("**Whole dataset bundle**")
    c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
    bundle = c1.file_uploader("Upload a ZIP of CSV files named after the datasets (courses.csv, occupations.csv, ...)", type=["zip"], key="zip_up")
    if bundle is not None and bundle.file_id not in ss.seen_uploads:
        ss.seen_uploads.add(bundle.file_id)
        try:
            found, skipped = frames_from_zip(bundle.getvalue())
            for k, df in found.items():
                set_draft(k, df)
            st.toast(f"Loaded {len(found)} dataset(s) into the draft: {', '.join(found) or 'none'}", icon=":material/upload:")
            if skipped:
                st.toast("Skipped: " + ", ".join(skipped[:5]), icon=":material/warning:")
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not read ZIP: {e}")
    with c2.container(horizontal=True):
        st.download_button("Download active bundle", bundle_to_zip(ss.frames), "coursepath_data.zip", "application/zip", icon=":material/download:")
        if st.button("Reset to defaults", icon=":material/restart_alt:"):
            d = default_frames()
            for k in SPECS:
                set_draft(k, d[k])
            activate(d)
            st.toast("Default data restored", icon=":material/restart_alt:")
            st.rerun()

# --------------------------------------------------------------- one dataset
names = list(SPECS)
name = st.selectbox(
    "Dataset",
    names,
    format_func=lambda k: f"{SPECS[k].title}" + (" (optional)" if SPECS[k].optional_dataset else ""),
    key="dataset_choice",
)
spec = SPECS[name]
edited_mark = " :orange-badge[edited, not applied]" if not ss.draft[name].equals(ss.frames[name]) else ""
st.caption(spec.description + edited_mark)
cols_info = []
if spec.required:
    cols_info.append("Required columns: " + ", ".join(f"`{c}`" for c in spec.required))
if spec.optional:
    cols_info.append("Optional: " + ", ".join(f"`{c}`" for c in spec.optional))
if cols_info:
    st.caption(" · ".join(cols_info))

c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
up = c1.file_uploader(f"Upload {spec.title.lower()}", type=["csv", "tsv", "txt", "xlsx", "xls", "json"], key=f"up_{name}")
if up is not None and up.file_id not in ss.seen_uploads:
    ss.seen_uploads.add(up.file_id)
    try:
        set_draft(name, read_table(up.name, up.getvalue()))
        st.toast(f"Loaded {len(ss.draft[name])} rows from {up.name}", icon=":material/upload:")
    except Exception as e:  # noqa: BLE001
        st.error(f"Could not read {up.name}: {e}")
with c2.container(horizontal=True):
    st.download_button("Template", sample_frame(name).to_csv(index=False), f"{name}_template.csv", "text/csv", icon=":material/description:")
    st.download_button("Current", ss.draft[name].to_csv(index=False), f"{name}.csv", "text/csv", icon=":material/download:")
    if spec.optional_dataset and st.button("Clear", icon=":material/delete:"):
        set_draft(name, pd.DataFrame())
        st.rerun()
    if st.button("Undo edits", icon=":material/undo:"):
        set_draft(name, ss.frames[name].copy())
        st.rerun()

if ss.draft[name].empty and spec.optional_dataset:
    st.info("Not provided. The app uses simulated values instead. Upload a file or start from the template.", icon=":material/info:")
    if st.button("Start from template", icon=":material/add:"):
        set_draft(name, sample_frame(name))
        st.rerun()
else:
    edited = st.data_editor(
        ss.base[name],
        num_rows="dynamic",
        hide_index=True,
        key=f"ed_{name}_{ss.draft_ver[name]}",
        alt=f"Editable {spec.title} table",
    )
    ss.draft[name] = edited.dropna(how="all").reset_index(drop=True)
    st.caption(f"{len(ss.draft[name])} rows · {len(ss.draft[name].columns)} columns · add or delete rows at the bottom of the table")

# ------------------------------------------------------------------ validation
report = validate(ss.draft)
errors = has_errors(report)
changed = [k for k in SPECS if not ss.draft[k].equals(ss.frames[k])]

with st.container(border=True):
    st.markdown("**Validation of the draft**")
    any_msg = False
    for k, msgs in report.items():
        for sev, msg in msgs:
            any_msg = True
            (st.error if sev == "error" else st.warning)(f"**{SPECS[k].title}:** {msg}")
    if not any_msg:
        st.success("All datasets are consistent.", icon=":material/check_circle:")
    with st.container(horizontal=True, vertical_alignment="center"):
        if st.button("Apply to the whole app", type="primary", icon=":material/check:", disabled=errors or not changed):
            activate(ss.draft)
            for k in SPECS:  # the applied data becomes the new editing base
                set_draft(k, ss.frames[k].copy())
            st.toast("Data applied. Planner state was reset.", icon=":material/check_circle:")
            st.rerun()
        if changed:
            st.caption("Changed: " + ", ".join(SPECS[k].title for k in changed))
        elif not errors:
            st.caption("Draft matches the active data.")
    if errors:
        st.caption("Fix the errors above to apply.")

with st.expander("Active data summary", icon=":material/dataset:"):
    cat, mk = ss.catalog, ss.market
    st.table(pd.DataFrame({
        "Item": ["Program", "Courses", "Required courses", "Electives", "Gen-ed choices", "Career goals", "Seasons",
                 "Skills", "Occupations", "Training courses", "Uploaded students", "Registrar seat records",
                 "Courses with resource links", "Resource search sites"],
        "Value": [cat.requirements.program, len(cat.courses), len(cat.required), len(cat.electives), len(cat.geneds),
                  len(cat.careers), ", ".join(cat.requirements.seasons), len(mk.skills), len(mk.occupations),
                  len(mk.training), len(mk.students), len(cat.seat_overrides),
                  len(cat.resources), len(cat.resource_links)],
    }).astype(str), alt="Counts of the active datasets")
