"""University curricula: subjects per branch and semester, with a learning
roadmap built from each subject's syllabus units.

Each university is a folder holding:
- ``meta.json``: {"name", "short_name", "source", "added_by", "added_at", "built_in"}
- ``curriculum.csv``: branch, semester, code, title, category, ltp, credits
  (elective slots have an empty code)
- ``syllabus.json``: {code: {"units": [...], "textbooks": [...]}}

Built-in universities live in ``data/universities/`` (in git). Universities that
users add from PDFs live next to the accounts in ``auth/universities/``
(git-ignored), so they survive code updates but not a wiped disk.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd

from .auth import auth_dir

DATA_DIR = Path(os.environ.get("COURSEPATH_DATA_DIR", Path(__file__).resolve().parents[1] / "data"))
COLUMNS = ["branch", "semester", "code", "title", "category", "ltp", "credits"]
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


def builtin_dir() -> Path:
    return DATA_DIR / "universities"


def uploads_dir() -> Path:
    return auth_dir() / "universities"


@dataclass(frozen=True)
class University:
    slug: str
    name: str
    short_name: str
    source: str
    built_in: bool
    added_by: str
    added_by_name: str
    path: Path
    term_names: dict = None  # e.g. {"1": "T1", "4": "Summer 1"}; default "Sem N"
    term_word: str = "Semester"

    def term_label(self, n: int) -> str:
        return (self.term_names or {}).get(str(n), f"Sem {n}")


def _read_meta(folder: Path, built_in: bool) -> University | None:
    try:
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not (folder / "curriculum.csv").exists():
        return None
    name = str(meta.get("name") or folder.name)
    return University(folder.name, name, str(meta.get("short_name") or name), str(meta.get("source", "")),
                      built_in, str(meta.get("added_by", "")), str(meta.get("added_by_name", "")), folder,
                      dict(meta.get("term_names") or {}), str(meta.get("term_word") or "Semester"))


def _meta_order(folder: Path) -> int:
    try:
        return int(json.loads((folder / "meta.json").read_text(encoding="utf-8")).get("order", 99))
    except (OSError, ValueError, json.JSONDecodeError):
        return 99


def list_universities() -> list[University]:
    """Built-in universities first, then uploaded ones (oldest first)."""
    out = []
    for base, built_in in ((builtin_dir(), True), (uploads_dir(), False)):
        if not base.exists():
            continue
        folders = sorted((p for p in base.iterdir() if p.is_dir()),
                         key=(lambda p: (_meta_order(p), p.name)) if built_in else (lambda p: p.stat().st_mtime))
        for f in folders:
            u = _read_meta(f, built_in)
            if u and not any(x.slug == u.slug for x in out):
                out.append(u)
    return out


def get_university(slug: str) -> University | None:
    return next((u for u in list_universities() if u.slug == slug), None)


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "university"
    taken = {u.slug for u in list_universities()}
    base, n = s, 2
    while s in taken:
        s = f"{base}-{n}"
        n += 1
    return s


def save_university(name: str, short_name: str, curriculum: pd.DataFrame, syllabus: dict, *, source: str,
                    added_by: str, added_by_name: str = "") -> University:
    """Write a new uploaded university and return it."""
    df = clean_curriculum(curriculum)
    if df.empty:
        raise ValueError("The course table is empty.")
    slug = slugify(short_name or name)
    folder = uploads_dir() / slug
    folder.mkdir(parents=True, exist_ok=False)
    meta = {"name": name.strip(), "short_name": (short_name or name).strip(), "source": source,
            "added_by": added_by, "added_by_name": added_by_name, "added_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "built_in": False}
    (folder / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    df.to_csv(folder / "curriculum.csv", index=False)
    keep = {c: v for c, v in syllabus.items() if c in set(df["code"])}
    (folder / "syllabus.json").write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
    return _read_meta(folder, False)


def delete_university(slug: str) -> bool:
    """Remove an uploaded university. Built-in ones can't be deleted."""
    u = get_university(slug)
    if not u or u.built_in or not SLUG_RE.match(slug):
        return False
    shutil.rmtree(u.path)
    return True


def clean_curriculum(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise an edited course table: required columns, text values, valid semester numbers."""
    df = df.copy()
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = ""
    df = df[COLUMNS].fillna("").astype(str)
    for c in COLUMNS:
        df[c] = df[c].str.strip()
    df["semester"] = pd.to_numeric(df["semester"], errors="coerce")
    df = df[df["title"].ne("") & df["branch"].ne("") & df["semester"].between(1, 12)]
    df["semester"] = df["semester"].astype(int)
    return df.reset_index(drop=True)


LAB_WORDS = ("Lab", "Laboratory", "Practice")
PROJECT_WORDS = ("Project", "Internship", "Live-in", "Term Paper")
ACTIVITY_WORDS = ("Activity Points", "Advising Seminar", "Industry Certification", "Value Added Course")
SLOT_RE = re.compile(r"\belective\b|^minor\b", re.I)

# Used when a university publishes course names but no syllabus units.
GENERAL_OUTLINE = (
    "Foundations: the key terms, ideas and notation of {t}, and why the subject matters",
    "Core concepts: the main methods, models and techniques taught in {t}",
    "Applying it: worked examples, problems and small hands-on tasks in {t}",
    "Practice and revision: previous exam questions, quizzes and a summary sheet for {t}",
)


@dataclass(frozen=True)
class Subject:
    branch: str
    semester: int
    code: str
    title: str
    category: str
    ltp: str
    credits: str
    units: tuple[str, ...] = ()
    textbooks: tuple[str, ...] = ()
    resources: tuple[tuple[str, str], ...] = ()  # (label, url) the university itself recommends
    project: str = ""  # the course's project, for project-based curricula

    @property
    def is_elective_slot(self) -> bool:
        return not self.code and bool(SLOT_RE.search(self.title))

    @property
    def kind(self) -> str:
        if self.is_elective_slot:
            return "Elective"
        if any(w in self.title for w in PROJECT_WORDS):
            return "Project"
        if any(w in self.title for w in LAB_WORDS):
            return "Lab"
        if any(w in self.title for w in ACTIVITY_WORDS):
            return "Activity"
        return "Theory"

    @property
    def credit_value(self) -> float:
        try:
            return float(self.credits)
        except ValueError:
            return 0.0

    @property
    def has_official_syllabus(self) -> bool:
        return bool(self.units)

    @property
    def outline(self) -> tuple[str, ...]:
        """Roadmap steps: the official syllabus units, or a general outline for theory subjects without one."""
        if self.units:
            return self.units
        if self.kind == "Theory":
            return tuple(s.format(t=self.title) for s in GENERAL_OUTLINE)
        return ()


def load_curriculum(uni: University | None = None) -> pd.DataFrame:
    uni = uni or default_university()
    p = uni.path / "curriculum.csv" if uni else None
    if not p or not p.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(p, dtype=str).fillna("")
    df["semester"] = df["semester"].astype(int)
    return df


def load_syllabus(uni: University | None = None) -> dict:
    uni = uni or default_university()
    p = uni.path / "syllabus.json" if uni else None
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p and p.exists() else {}
    except json.JSONDecodeError:
        return {}


def default_university() -> University | None:
    unis = list_universities()
    return unis[0] if unis else None


def load_study_sites() -> list[tuple[str, str]]:
    """(name, url_template) for learning sites searched for every subject; ``{query}`` is the subject name."""
    p = DATA_DIR / "resource_links.csv"
    if not p.exists():
        return []
    df = pd.read_csv(p, dtype=str).fillna("")
    return [(r["name"], r["url_template"]) for _, r in df.iterrows()
            if r["url_template"].startswith(("http://", "https://")) and "{query}" in r["url_template"]]


def branches(df: pd.DataFrame) -> list[str]:
    return list(dict.fromkeys(df["branch"]))


def semesters(df: pd.DataFrame, branch: str) -> list[int]:
    return sorted(df.loc[df["branch"] == branch, "semester"].unique().tolist())


def subjects(df: pd.DataFrame, syllabus: dict, branch: str, semester: int) -> list[Subject]:
    rows = df[(df["branch"] == branch) & (df["semester"] == semester)]
    out = []
    for r in rows.itertuples(index=False):
        s = syllabus.get(r.code, {})
        out.append(Subject(r.branch, int(r.semester), r.code, r.title, r.category, r.ltp, r.credits,
                           tuple(s.get("units", ())), tuple(s.get("textbooks", ())),
                           tuple((str(x.get("label", "")), str(x.get("url", ""))) for x in s.get("resources", ())
                                 if str(x.get("url", "")).startswith("https://")),
                           str(s.get("project", ""))))
    return out


def step_title(unit: str, words: int = 8) -> str:
    """A short heading for a syllabus unit: its lead phrase, or its first few words."""
    head = re.split(r"\s[-–]\s|;|:|\.\s|,", unit, maxsplit=1)[0].strip()
    parts = head.split()
    if 1 <= len(parts) <= words:
        return head
    return " ".join(unit.split()[:words]) + "…"


def topic_query(subject_title: str, unit: str) -> str:
    """Search text for one roadmap step: subject title plus the step's lead topic."""
    lead = re.sub(r"\(.*?\)", "", subject_title).strip()
    return f"{lead} {step_title(unit, 6).rstrip('…')}"


def search_url(template: str, query: str) -> str:
    return template.replace("{query}", quote_plus(query))


def youtube_url(query: str) -> str:
    return search_url("https://www.youtube.com/results?search_query={query}", query)


def nptel_url(query: str) -> str:
    return youtube_url(f"NPTEL {query}")
