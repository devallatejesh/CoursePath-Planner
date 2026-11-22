"""Search any subject across every university and pick the best roadmap for it.

The index holds every subject of every university (built-in and added). A search
ranks them by how well the title (and, more weakly, the syllabus text) matches
the query, using word overlap with light stemming plus fuzzy title similarity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from .curriculum import Subject, branches, list_universities, load_curriculum, load_syllabus, semesters, subjects

STOP = {"and", "of", "the", "for", "to", "in", "with", "a", "an", "on", "using", "through", "introduction", "intro",
        "fundamentals", "foundations", "basics", "principles", "engineering", "engineers", "i", "ii", "iii", "iv",
        "1", "2", "3", "4", "course", "lab", "laboratory"}
ALIASES = {
    "dsa": "data structures algorithms", "ds": "data structures", "daa": "design analysis algorithms",
    "os": "operating systems", "cn": "computer networks", "dbms": "database management systems",
    "ml": "machine learning", "dl": "deep learning", "ai": "artificial intelligence", "nlp": "natural language processing",
    "cv": "computer vision", "toc": "theory computation automata", "coa": "computer organization architecture",
    "oop": "object oriented programming", "oops": "object oriented programming", "dsp": "digital signal processing",
    "vlsi": "vlsi design", "iot": "internet things iot", "genai": "generative ai", "llm": "large language models",
    "se": "software engineering", "cd": "compiler design", "de": "digital electronics", "dld": "digital logic design",
    "web": "web development", "fsd": "full stack development", "devops": "devops ci cd", "cyber": "cyber security",
}


def _stem(w: str) -> str:
    for suf in ("ations", "ation", "ing", "ies", "es", "s"):
        if len(w) > 5 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9+#]+", text.lower())
    out = set()
    for w in words:
        for x in ALIASES.get(w, w).split():
            if x not in STOP:
                out.add(_stem(x))
    return out


def clean_title(title: str) -> str:
    return re.sub(r"\s*[-–]\s*\d+$|\s+\d+$|\s+[IVX]+$|\(.*?\)", "", title).strip()


@dataclass(frozen=True)
class Hit:
    score: float
    subject: Subject
    uni_slug: str
    uni_name: str
    term: str  # e.g. "Sem 3" or "T4"


def build_index() -> list[tuple[Subject, str, str, str]]:
    """(subject, university slug, university short name, term label) for every subject of every university."""
    rows = []
    for u in list_universities():
        df, syl = load_curriculum(u), load_syllabus(u)
        for b in branches(df):
            for sem in semesters(df, b):
                for s in subjects(df, syl, b, sem):
                    if s.is_elective_slot:
                        continue
                    rows.append((s, u.slug, u.short_name, u.term_label(sem)))
    return rows


def score(query: str, s: Subject) -> float:
    q, t = tokens(query), tokens(s.title)
    if not q or not t:
        return 0.0
    overlap = len(q & t)
    title_score = overlap / len(q) * 0.7 + overlap / len(t) * 0.3
    if overlap < len(q):
        title_score *= 0.6  # every query word should be in the title for a strong match
    fuzzy = SequenceMatcher(None, query.lower().strip(), clean_title(s.title).lower()).ratio()
    if fuzzy < 0.8:
        fuzzy = 0.0  # only near-identical spellings (typos) count; otherwise rely on shared words
    body = 0.0
    if s.units and 0 < overlap < len(q):
        blob = tokens(" ".join(s.units))
        body = len(q & blob) / len(q) * 0.15
    kind_bonus = {"Theory": 0.05, "Lab": -0.1, "Project": -0.3, "Activity": -0.3}.get(s.kind, 0.0)
    return round(max(title_score, fuzzy * 0.9) + body + (0.05 if s.units else 0.0) + kind_bonus, 4)


def search(query: str, index, limit: int = 12, min_score: float = 0.45) -> list[Hit]:
    """Best matches first; one per (university, title) so the same subject in many branches shows once."""
    hits, seen = [], set()
    scored = sorted(((score(query, s), s, slug, name, term) for s, slug, name, term in index), key=lambda x: -x[0])
    for sc, s, slug, name, term in scored:
        if sc < min_score:
            break
        key = (slug, clean_title(s.title).lower())
        if key in seen:
            continue
        seen.add(key)
        hits.append(Hit(sc, s, slug, name, term))
        if len(hits) >= limit:
            break
    return hits


def best_roadmap(hits: list[Hit], min_score: float = 0.7) -> Hit | None:
    """The strongest close match that has an official syllabus (most steps wins a near tie).
    Partial matches (only some query words in the title) are not used as the roadmap."""
    with_units = [h for h in hits if h.subject.has_official_syllabus and h.subject.kind == "Theory" and h.score >= min_score]
    if not with_units:
        return None
    top = with_units[0].score
    close = [h for h in with_units if h.score >= top - 0.05]
    return max(close, key=lambda h: (len(h.subject.units), h.score))


def popular_titles(index, n: int = 12) -> list[str]:
    """Subjects with an official roadmap taught at the most universities - used as quick suggestions."""
    count: dict[str, set] = {}
    for s, slug, _, _ in index:
        if s.has_official_syllabus and s.kind == "Theory":
            count.setdefault(clean_title(s.title), set()).add(slug)
    ranked = sorted(count.items(), key=lambda kv: (-len(kv[1]), len(kv[0])))
    return [t for t, _ in ranked[:n]]
