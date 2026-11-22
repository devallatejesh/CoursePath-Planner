import streamlit as st

from core.curriculum import (
    Subject, list_universities, load_study_sites, nptel_url, search_url, step_title, topic_query, youtube_url,
)
from core.resources import is_dsa, recommended
from core.subject_search import best_roadmap, build_index, popular_titles, search
from core.viz import md_escape

ss = st.session_state
SITE_ICON = {"W3Schools": ":material/code:", "GeeksforGeeks": ":material/terminal:", "Striver": ":material/fitness_center:",
             "YouTube": ":material/smart_display:"}


@st.cache_data(show_spinner="Building the subject index...")
def _index(stamp: tuple):
    return build_index()


def _stamp() -> tuple:
    """Changes whenever a university is added, removed or edited, so the index refreshes."""
    out = []
    for u in list_universities():
        p = u.path / "curriculum.csv"
        out.append((u.slug, p.stat().st_mtime if p.exists() else 0))
    return tuple(out)


def roadmap(steps, title: str):
    for i, unit in enumerate(steps, 1):
        q = topic_query(title, unit)
        st.markdown(f"**Step {i}: {md_escape(step_title(unit))}**")
        st.markdown(md_escape(unit))
        st.markdown(f":material/play_circle: [YouTube videos for this step]({youtube_url(q)}) · [NPTEL]({nptel_url(q)})")
        if i < len(steps):
            st.divider()


index = _index(_stamp())
pages = ss.get("uni_pages", {})

st.title("Subject search", anchor=False)
st.caption("Type any subject to get a step-by-step learning roadmap and study resources, no university needed. "
           "Roadmaps come from the closest official syllabus among all universities in the app.")

if "subject_query" not in ss:
    ss.subject_query = ""
pick = st.pills("Popular subjects", popular_titles(index, 12), key="subject_pick", selection_mode="single")
if pick and pick != ss.get("_last_pick"):
    ss.subject_query = pick
ss._last_pick = pick
query = st.text_input("Subject", key="subject_query", placeholder="e.g. Operating Systems, DSA, Machine Learning, VLSI, Cryptography",
                      icon=":material/search:").strip()

if not query:
    st.info(f"Search {len(index)} subjects from {len(list_universities())} universities, or pick a popular one above.",
            icon=":material/travel_explore:")
    st.stop()

hits = search(query, index)
best = best_roadmap(hits)
subject = best.subject if best else Subject("", 0, "", query.strip().title(), "", "", "")
display = subject.title if best else query.strip()

st.header(f"Roadmap: {display}", anchor=False)
if best:
    st.caption(f"From the official {md_escape(best.subject.title)} syllabus at **{md_escape(best.uni_name)}** "
               f"({md_escape(best.subject.branch)}, {md_escape(best.term)}).")
else:
    st.info("No university in the app has a syllabus for this exact subject, so this is a general study outline. "
            "The resources below are still matched to your search.", icon=":material/info:")

tab_map, tab_res, tab_where = st.tabs([":material/route: Roadmap", ":material/library_books: Resources",
                                       f":material/school: Where it's taught ({len(hits)})"])

with tab_map:
    roadmap(subject.outline, display)
    if is_dsa(display):
        st.caption("Practise the matching topics from Striver's A2Z DSA sheet alongside each step.")
    if subject.project:
        st.caption(f":material/construction: Project idea: {md_escape(subject.project)}")

with tab_res:
    picks = recommended(display if best else query)
    st.markdown("**Recommended**")
    for site, label, url in picks:
        st.markdown(f"- {SITE_ICON.get(site, '')} [{md_escape(site)}: {md_escape(label)}]({url})")
    if subject.resources:
        st.markdown(f"**{md_escape(best.uni_name)} recommends**")
        for label, url in subject.resources:
            st.markdown(f"- [{md_escape(label)}]({url})")
    st.markdown("**More study links**")
    more = [("NPTEL lectures", nptel_url(display))] + [(n, search_url(t, display)) for n, t in load_study_sites()]
    st.markdown(" · ".join(f"[{md_escape(n)}]({u})" for n, u in more))
    if subject.textbooks:
        st.markdown("**Textbooks**")
        for b in subject.textbooks:
            st.markdown(f"- {md_escape(b)}")

with tab_where:
    if not hits:
        st.caption("No university in the app lists a subject like this yet.")
    for h in hits:
        s = h.subject
        label = f"{s.title} · {h.uni_name} · {s.branch} · {h.term}"
        with st.expander(label, icon=":material/menu_book:" if s.units else ":material/description:"):
            meta = [f":blue-badge[{md_escape(s.category)}]"] if s.category else []
            if s.credits:
                meta.append(f":green-badge[{md_escape(s.credits)} credits]")
            meta.append(f":violet-badge[{s.kind}]")
            st.markdown(" ".join(meta) + (f" · `{s.code}`" if s.code else ""))
            if s.units:
                for i, unit in enumerate(s.units, 1):
                    st.markdown(f"{i}. **{md_escape(step_title(unit))}**: {md_escape(unit[:220])}{'…' if len(unit) > 220 else ''}")
            else:
                st.caption("No syllabus units published for this subject.")
            if h.uni_slug in pages:
                st.page_link(pages[h.uni_slug], label=f"Open {h.uni_name}", icon=":material/arrow_forward:")
