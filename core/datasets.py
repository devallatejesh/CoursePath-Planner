"""Dataset bundle: load defaults, read uploads, validate, and build the planner
catalog and the simulation's market data from plain tables.

Every table lives in ``data/<name>.csv`` by default and can be replaced from
the Data manager page (CSV, Excel or JSON, or a ZIP of several CSVs).
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

from .catalog import Career, Catalog, Course, DegreeRequirements

import os
import shutil
from datetime import datetime

DATA_DIR = Path(os.environ.get("COURSEPATH_DATA_DIR", Path(__file__).resolve().parents[1] / "data"))
BACKUP_DIR = DATA_DIR / "backups"


@dataclass(frozen=True)
class Spec:
    title: str
    description: str
    required: tuple[str, ...]
    optional: dict  # column -> default
    optional_dataset: bool = False  # the app works without it
    list_columns: tuple[str, ...] = ()


SPECS: dict[str, Spec] = {
    "courses": Spec(
        "Course catalog",
        "One row per course. Lists (prereqs, coreqs, tags) are separated by `;`. "
        "`terms` holds the first letters of the seasons it runs in (e.g. `FS`).",
        ("code", "name", "credits", "category"),
        {"prereqs": "", "coreqs": "", "terms": "FS", "tags": "", "pass_rate": 0.9, "capacity": 60, "counts": 1},
        list_columns=("prereqs", "coreqs", "tags"),
    ),
    "requirements": Spec(
        "Degree requirements",
        "Key/value rules for the degree audit and planner limits.",
        ("key", "value"),
        {"description": ""},
    ),
    "careers": Spec(
        "Career goals",
        "Career goals students can pick. `track` must match course tags; `keywords` drive the goal interpreter.",
        ("name",),
        {"track": "", "tags": "", "median_salary_k": 0, "keywords": ""},
        list_columns=("tags", "keywords"),
    ),
    "occupations": Spec(
        "Occupations (simulation)",
        "Job-market roles. Every extra numeric column is a skill (0-1 required level), e.g. from O*NET.",
        ("name",),
        {"salary_k": 80, "automation_risk": 0.2, "base_demand": 1.0, "tags": ""},
        list_columns=("tags",),
    ),
    "training": Spec(
        "Training courses (simulation)",
        "Courses offered by training providers. Skill columns hold the boost each course gives.",
        ("name", "duration_months"),
        {},
    ),
    "tag_skills": Spec(
        "Course-to-skill mapping",
        "How much each course tag (`tag:ai`) or category (`category:math`) adds to each skill. Used to turn a roadmap into a skill profile.",
        ("key",),
        {},
    ),
    "students": Spec(
        "Student survey (optional)",
        "Real or surveyed students for the simulation: one row per student with skill columns, "
        "optional `favourite_occupation` and `planned` (1 = has an advisor).",
        (),
        {"student_id": "", "favourite_occupation": "", "planned": ""},
        optional_dataset=True,
    ),
    "seats": Spec(
        "Registrar seats (optional)",
        "Live seat availability: `code`, `term` (e.g. `Fall 2026`), `seats_open`. Overrides the simulated registrar.",
        ("code", "term", "seats_open"),
        {},
        optional_dataset=True,
    ),
    "resources": Spec(
        "Course resources",
        "Specific study links shown under each subject: `code`, `url`, optional `title` and `type` "
        "(reading, video, course, practice...). A course can have several rows.",
        ("code", "url"),
        {"title": "", "type": "reading"},
        optional_dataset=True,
    ),
    "resource_links": Spec(
        "Resource search links",
        "Learning sites searched for every subject. `{query}` in `url_template` is replaced by the course name.",
        ("name", "url_template"),
        {"type": "search"},
        optional_dataset=True,
    ),
    "literature": Spec(
        "Literature survey",
        "Studies shown on the Literature page. Any columns are allowed.",
        (),
        {},
    ),
}

REQUIREMENT_DEFAULTS = {
    "program": "Degree program",
    "required_categories": "core",
    "required_courses": "",
    "gened_category": "gened",
    "gened_choices": 0,
    "elective_category": "elective",
    "track_electives": 0,
    "free_electives": 0,
    "hard_threshold": 0.8,
    "max_hard_per_term": 2,
    "max_hard_if_avoiding": 1,
    "seasons": "Fall;Spring",
    "new_year_season": "Spring",
}

OCC_META = {"name", "salary_k", "automation_risk", "base_demand", "tags"}
STUDENT_META = {"student_id", "favourite_occupation", "planned"}


# ----------------------------------------------------------------- reading
def split_list(v) -> tuple[str, ...]:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ()
    return tuple(x.strip() for x in re.split(r"[;,|]", str(v)) if x.strip())


def as_text(v) -> str:
    """Cell -> clean text; 101.0 -> '101' so numeric course codes still match."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ""
    if isinstance(v, (float, np.floating)) and float(v).is_integer():
        return str(int(v))
    return str(v).strip()


def is_url(v) -> bool:
    t = as_text(v).lower()
    return t.startswith(("http://", "https://")) and " " not in t.strip() and len(t) > 10


def parse_bool(v):
    """1/0, yes/no, true/false, y/n -> 1.0/0.0; blank -> None; anything else raises."""
    t = as_text(v).lower()
    if t == "":
        return None
    if t in ("1", "yes", "y", "true", "t", "planned"):
        return 1.0
    if t in ("0", "no", "n", "false", "f", "unplanned"):
        return 0.0
    f = float(t)
    if not 0 <= f <= 1:
        raise ValueError(t)
    return f


TEXT_COLUMNS = {
    "courses": ("code", "name", "prereqs", "coreqs", "terms", "category", "tags"),
    "careers": ("name", "track", "tags", "keywords"),
    "occupations": ("name", "tags"),
    "training": ("name",),
    "tag_skills": ("key",),
    "students": ("student_id", "favourite_occupation"),
    "seats": ("code", "term"),
    "resources": ("code", "url", "title", "type"),
    "resource_links": ("name", "url_template", "type"),
}
NUMERIC_COLUMNS = {
    "courses": ("credits", "pass_rate", "capacity"),
    "careers": ("median_salary_k",),
    "occupations": ("salary_k", "automation_risk", "base_demand"),
    "training": ("duration_months",),
    "seats": ("seats_open",),
}


def clean(key: str, df: pd.DataFrame) -> pd.DataFrame:
    """Coerce code-like columns to text so 101 / 101.0 / '101' all match."""
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()
    df = df.copy()
    for col in TEXT_COLUMNS.get(key, ()):
        if col in df.columns:
            df[col] = df[col].map(as_text)
    return df


def bad_numbers(df: pd.DataFrame, cols) -> dict[str, list[int]]:
    """Columns holding non-numeric values (blank cells are allowed) -> 1-based row numbers."""
    out = {}
    for col in cols:
        if col not in df.columns:
            continue
        raw = df[col]
        num = pd.to_numeric(raw, errors="coerce")
        blank = raw.isna() | (raw.astype(str).str.strip() == "")
        rows = [i + 1 for i in np.flatnonzero((num.isna() & ~blank).to_numpy())]
        if rows:
            out[col] = rows
    return out


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [re.sub(r"\s+", "_", str(c).strip().lower()) for c in df.columns]
    df = df.dropna(how="all")
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].map(lambda x: x.strip() if isinstance(x, str) else x)
    return df.reset_index(drop=True)


def read_table(name: str, data: bytes) -> pd.DataFrame:
    low = name.lower()
    if low.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(data))
    elif low.endswith(".json"):
        df = pd.read_json(io.BytesIO(data))
    else:
        df = pd.read_csv(io.BytesIO(data), sep=None, engine="python")  # sniff , ; or tab
    return normalise(df)


def load_defaults() -> dict[str, pd.DataFrame]:
    frames = {}
    for key in SPECS:
        p = DATA_DIR / f"{key}.csv"
        frames[key] = normalise(pd.read_csv(p)) if p.exists() else pd.DataFrame()
    return frames


def sample_frame(key: str) -> pd.DataFrame:
    p = DATA_DIR / "samples" / f"{key}_sample.csv"
    if p.exists():
        return pd.read_csv(p)
    p = DATA_DIR / f"{key}.csv"
    if p.exists():
        return pd.read_csv(p).head(5)
    spec = SPECS[key]
    return pd.DataFrame(columns=list(spec.required) + list(spec.optional))


def fingerprint(frames: dict[str, pd.DataFrame]) -> str:
    h = hashlib.sha1()
    for k in sorted(frames):
        df = frames[k]
        h.update(k.encode())
        h.update(df.to_csv(index=False).encode())
    return h.hexdigest()[:12]


def bundle_to_zip(frames: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for k, df in frames.items():
            if not df.empty:
                z.writestr(f"{k}.csv", df.to_csv(index=False))
    return buf.getvalue()


def frames_from_zip(data: bytes) -> tuple[dict[str, pd.DataFrame], list[str]]:
    found, skipped = {}, []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            stem = Path(info.filename).stem.lower()
            if stem in SPECS and Path(info.filename).suffix.lower() in (".csv", ".xlsx", ".xls", ".json"):
                found[stem] = read_table(info.filename, z.read(info))
            else:
                skipped.append(info.filename)
    return found, skipped


# --------------------------------------------------------------- helpers
def requirement_values(frames) -> dict:
    df = frames.get("requirements", pd.DataFrame())
    vals = dict(REQUIREMENT_DEFAULTS)
    if not df.empty and {"key", "value"} <= set(df.columns):
        for k, v in zip(df["key"], df["value"]):
            if isinstance(k, str) and pd.notna(v):
                vals[k.strip()] = v
    return vals


def skill_columns(df: pd.DataFrame, meta: set[str]) -> list[str]:
    return [c for c in df.columns if c not in meta and pd.api.types.is_numeric_dtype(df[c])]


def numeric_frame(df: pd.DataFrame, cols) -> pd.DataFrame:
    """Copy of df with ``cols`` coerced to numbers (blank -> NaN)."""
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _with_defaults(df: pd.DataFrame, spec: Spec) -> pd.DataFrame:
    df = df.copy()
    for col, default in spec.optional.items():
        if col not in df.columns:
            df[col] = default
        else:
            df[col] = df[col].where(df[col].notna(), default)
    return df


# --------------------------------------------------------------- validation
def validate(frames: dict[str, pd.DataFrame]) -> dict[str, list[tuple[str, str]]]:
    """Return {dataset: [(severity, message), ...]} for the whole bundle."""
    out: dict[str, list[tuple[str, str]]] = {k: [] for k in SPECS}
    frames = {k: clean(k, v) for k, v in frames.items()}

    def err(k, m):
        out[k].append(("error", m))

    def warn(k, m):
        out[k].append(("warning", m))

    for k, spec in SPECS.items():
        df = frames.get(k, pd.DataFrame())
        if df.empty:
            if not spec.optional_dataset and k != "literature":
                err(k, "Dataset is empty")
            continue
        missing = [c for c in spec.required if c not in df.columns]
        if missing:
            err(k, "Missing column(s): " + ", ".join(missing))
        for col, rows in bad_numbers(df, NUMERIC_COLUMNS.get(k, ())).items():
            err(k, f"`{col}` must be a number (row {', '.join(map(str, rows[:5]))}{'...' if len(rows) > 5 else ''})")

    req = requirement_values(frames)
    seasons = split_list(req["seasons"])
    if not seasons:
        err("requirements", "`seasons` must list at least one term name, e.g. Fall;Spring")
    letters = [s[0].upper() for s in seasons]
    if str(req["new_year_season"]) not in seasons:
        err("requirements", "`new_year_season` must be one of the seasons")
    if len(set(letters)) != len(letters):
        err("requirements", "Season names must start with different letters (used as term codes)")
    for key in ("gened_choices", "track_electives", "free_electives", "max_hard_per_term", "max_hard_if_avoiding"):
        try:
            int(float(req[key]))
        except (TypeError, ValueError):
            err("requirements", f"`{key}` must be a number")
    try:
        float(req["hard_threshold"])
    except (TypeError, ValueError):
        err("requirements", "`hard_threshold` must be a number")

    # courses
    c = frames.get("courses", pd.DataFrame())
    if not c.empty and not [m for sv, m in out["courses"] if sv == "error"]:
        c = _with_defaults(c, SPECS["courses"])
        codes = c["code"].astype(str)
        dup = codes[codes.duplicated()].unique()
        if len(dup):
            err("courses", "Duplicate course codes: " + ", ".join(dup))
        known = set(codes)
        g = nx.DiGraph()
        for _, r in c.iterrows():
            for col in ("prereqs", "coreqs"):
                bad = [x for x in split_list(r[col]) if x not in known]
                if bad:
                    err("courses", f"{r['code']}: unknown {col[:-1]} {', '.join(bad)}")
            for p in split_list(r["prereqs"]):
                g.add_edge(p, r["code"])
            bad_terms = set(str(r["terms"]).upper()) - set(letters)
            if bad_terms:
                err("courses", f"{r['code']}: term code(s) {''.join(sorted(bad_terms))} not in seasons {''.join(letters)}")
            try:
                if not 0 <= float(r["pass_rate"]) <= 1:
                    err("courses", f"{r['code']}: pass_rate must be between 0 and 1")
                if float(r["credits"]) <= 0:
                    err("courses", f"{r['code']}: credits must be positive")
            except (TypeError, ValueError):
                err("courses", f"{r['code']}: credits and pass_rate must be numbers")
        cycles = list(nx.simple_cycles(g))
        if cycles:
            err("courses", "Prerequisite cycle: " + " → ".join(cycles[0]))
        cats = set(c["category"].astype(str))
        for rc in split_list(req["required_categories"]):
            if rc not in cats:
                warn("requirements", f"Required category `{rc}` has no courses")
        for rc in split_list(req["required_courses"]):
            if rc not in known:
                err("requirements", f"Required course `{rc}` is not in the catalog")
        required = set(c.loc[c["category"].astype(str).isin(split_list(req["required_categories"])), "code"]) | set(split_list(req["required_courses"]))
        counts = c["counts"].map(lambda v: as_text(v).lower() not in ("0", "false", "no"))
        electives = c[(c["category"].astype(str) == str(req["elective_category"])) & ~c["code"].isin(required) & counts]
        geneds = c[(c["category"].astype(str) == str(req["gened_category"])) & ~c["code"].isin(required) & counts]
        try:
            if len(geneds) < int(float(req["gened_choices"])):
                err("requirements", f"Need {int(float(req['gened_choices']))} gen-ed choices but the catalog has only {len(geneds)} `{req['gened_category']}` course(s)")
        except (TypeError, ValueError):
            pass
        try:
            need = int(float(req["track_electives"])) + int(float(req["free_electives"]))
            if len(electives) < need:
                err("requirements", f"Need {need} electives but the catalog has only {len(electives)}")
            careers = frames.get("careers", pd.DataFrame())
            if not careers.empty and "name" in careers.columns:
                careers = _with_defaults(careers, SPECS["careers"])
                for _, r in careers.iterrows():
                    track = str(r["track"] or "").strip() or (split_list(r["tags"]) or ("",))[0]
                    n = sum(track in split_list(t) for t in electives["tags"])
                    if n < int(float(req["track_electives"])):
                        warn("careers", f"{r['name']}: only {n} elective(s) tagged `{track}` (need {int(float(req['track_electives']))})")
        except (TypeError, ValueError):
            pass

    # occupations
    o = frames.get("occupations", pd.DataFrame())
    skills: list[str] = []
    if not o.empty and "name" in o.columns:
        skills = skill_columns(o, OCC_META)
        if not skills:
            err("occupations", "No numeric skill columns found")
        elif ((o[skills] < 0) | (o[skills] > 1)).any().any():
            err("occupations", "Skill levels must be between 0 and 1")
        if o["name"].duplicated().any():
            err("occupations", "Duplicate occupation names")
    for k, meta in (("training", {"name", "duration_months"}), ("tag_skills", {"key"}), ("students", STUDENT_META)):
        df = frames.get(k, pd.DataFrame())
        if df.empty or not skills:
            continue
        for col, rows in bad_numbers(df, [x for x in skills if x in df.columns]).items():
            err(k, f"Skill `{col}` must be a number (row {', '.join(map(str, rows[:5]))})")
        if k == "students" and "planned" in df.columns:
            bad = []
            for i, v in enumerate(df["planned"]):
                try:
                    parse_bool(v)
                except ValueError:
                    bad.append(i + 1)
            if bad:
                err(k, f"`planned` must be 1/0, yes/no or blank (row {', '.join(map(str, bad[:5]))})")
        df = numeric_frame(df, skills)
        cols = skill_columns(df, meta)
        extra = [x for x in cols if x not in skills]
        if extra:
            warn(k, "Ignored columns not among occupation skills: " + ", ".join(extra))
        if k == "students" and not set(cols) & set(skills):
            err(k, "No skill columns matching the occupations dataset")
        if k == "students" and "favourite_occupation" in df.columns:
            bad = set(df["favourite_occupation"].dropna().astype(str)) - set(o["name"].astype(str)) - {""}
            if bad:
                warn(k, "Unknown favourite occupations (ignored): " + ", ".join(sorted(bad)[:5]))
    s = frames.get("seats", pd.DataFrame())
    r_df = frames.get("resources", pd.DataFrame())
    if not r_df.empty and "url" in r_df.columns:
        bad = [i + 1 for i, u in enumerate(r_df["url"]) if not is_url(u)]
        if bad:
            err("resources", f"`url` must start with http:// or https:// (row {', '.join(map(str, bad[:5]))})")
        if "code" in r_df.columns and "code" in frames.get("courses", pd.DataFrame()).columns:
            unknown = sorted(set(r_df["code"]) - set(frames["courses"]["code"].astype(str)) - {""})
            if unknown:
                warn("resources", "Links for unknown course codes (ignored): " + ", ".join(unknown[:5]))
    l_df = frames.get("resource_links", pd.DataFrame())
    if not l_df.empty and "url_template" in l_df.columns:
        for i, t in enumerate(l_df["url_template"]):
            if not is_url(t) or "{query}" not in t:
                err("resource_links", f"Row {i + 1}: `url_template` must be an http(s) URL containing {{query}}")
    courses_df = frames.get("courses", pd.DataFrame())
    if not s.empty and "code" in s.columns and "code" in courses_df.columns:
        bad = set(s["code"].astype(str)) - set(courses_df["code"].astype(str))
        if bad:
            warn("seats", "Unknown course codes (ignored): " + ", ".join(sorted(bad)[:5]))
    return out


def has_errors(report) -> bool:
    return any(s == "error" for msgs in report.values() for s, _ in msgs)


# ------------------------------------------------------------------ builders
def build_catalog(frames: dict[str, pd.DataFrame]) -> Catalog:
    req = requirement_values(frames)
    threshold = float(req["hard_threshold"])
    c = _with_defaults(clean("courses", frames["courses"]), SPECS["courses"])
    courses = {}
    for _, r in c.iterrows():
        code = str(r["code"])
        pr = float(r["pass_rate"])
        courses[code] = Course(
            code=code,
            name=str(r["name"]),
            credits=int(float(r["credits"])),
            prereqs=split_list(r["prereqs"]),
            coreqs=split_list(r["coreqs"]),
            terms=str(r["terms"]).upper() or "".join(s[0].upper() for s in split_list(req["seasons"])),
            category=str(r["category"]),
            tags=split_list(r["tags"]),
            pass_rate=pr,
            capacity=int(float(r["capacity"])),
            counts=str(r["counts"]).strip().lower() not in ("0", "false", "no", "0.0"),
            hard=pr < threshold,
        )
    requirements = DegreeRequirements(
        program=str(req["program"]),
        required_categories=split_list(req["required_categories"]),
        required_courses=split_list(req["required_courses"]),
        gened_category=str(req["gened_category"]),
        gened_choices=int(float(req["gened_choices"])),
        elective_category=str(req["elective_category"]),
        track_electives=int(float(req["track_electives"])),
        free_electives=int(float(req["free_electives"])),
        hard_threshold=threshold,
        max_hard_per_term=int(float(req["max_hard_per_term"])),
        max_hard_if_avoiding=int(float(req["max_hard_if_avoiding"])),
        seasons=split_list(req["seasons"]),
        new_year_season=str(req["new_year_season"]),
    )
    careers = {}
    cdf = numeric_frame(_with_defaults(clean("careers", frames["careers"]), SPECS["careers"]), ["median_salary_k"])
    for _, r in cdf.iterrows():
        tags = split_list(r["tags"])
        track = str(r["track"] or "").strip() or (tags[0] if tags else "")
        keywords = split_list(r["keywords"]) or (str(r["name"]).lower(),)
        careers[str(r["name"])] = Career(str(r["name"]), track, tags or (track,), float(r["median_salary_k"]) if pd.notna(r["median_salary_k"]) else 0.0, tuple(k.lower() for k in keywords))
    seats = {}
    s = clean("seats", frames.get("seats", pd.DataFrame()))
    if not s.empty and {"code", "term", "seats_open"} <= set(s.columns):
        s = numeric_frame(s, ["seats_open"])
        for _, r in s.iterrows():
            if r["code"] in courses and pd.notna(r["seats_open"]):
                seats[(r["code"], r["term"])] = int(r["seats_open"])
    resources: dict[str, list[tuple[str, str, str]]] = {}
    r_df = clean("resources", frames.get("resources", pd.DataFrame()))
    if not r_df.empty and {"code", "url"} <= set(r_df.columns):
        r_df = _with_defaults(r_df, SPECS["resources"])
        for _, r in r_df.iterrows():
            if r["code"] in courses and is_url(r["url"]):
                title = as_text(r["title"]) or as_text(r["url"]).split("//", 1)[-1].split("/", 1)[0]
                resources.setdefault(r["code"], []).append((title, as_text(r["url"]), as_text(r["type"]) or "reading"))
    links: list[tuple[str, str, str]] = []
    l_df = clean("resource_links", frames.get("resource_links", pd.DataFrame()))
    if not l_df.empty and {"name", "url_template"} <= set(l_df.columns):
        l_df = _with_defaults(l_df, SPECS["resource_links"])
        for _, r in l_df.iterrows():
            if is_url(r["url_template"]) and "{query}" in r["url_template"]:
                links.append((as_text(r["name"]) or "Search", r["url_template"], as_text(r["type"]) or "search"))
    return Catalog(courses, requirements, careers, seats, resources, links)


@dataclass(frozen=True)
class OccSpec:
    name: str
    req: tuple[float, ...]
    salary_k: float
    automation_risk: float
    base_demand: float
    tags: tuple[str, ...]


@dataclass(frozen=True)
class MarketData:
    """Everything the MESA model needs. Frozen and non-iterable so it can be a
    fixed parameter in ``mesa.batch_run``."""

    skills: tuple[str, ...]
    occupations: tuple[OccSpec, ...]
    training: tuple[tuple[str, tuple[tuple[str, float], ...], int], ...]  # (name, boosts, months)
    tag_skills: tuple[tuple[str, tuple[tuple[str, float], ...]], ...]
    students: tuple[tuple[tuple[float, ...], str, float | None], ...] = ()  # (skills, favourite, planned)
    key: str = ""

    def training_dict(self) -> dict[str, tuple[dict[str, float], int]]:
        return {n: (dict(b), m) for n, b, m in self.training}

    def tag_skill_dict(self) -> dict[str, dict[str, float]]:
        return {k: dict(v) for k, v in self.tag_skills}


def build_market(frames: dict[str, pd.DataFrame]) -> MarketData:
    o = numeric_frame(_with_defaults(clean("occupations", frames["occupations"]), SPECS["occupations"]), ["salary_k", "automation_risk", "base_demand"])
    for col, default in SPECS["occupations"].optional.items():
        if col != "tags":
            o[col] = o[col].fillna(default)
    skills = tuple(skill_columns(o, OCC_META))
    o[list(skills)] = o[list(skills)].fillna(0.0)
    occs = tuple(
        OccSpec(str(r["name"]), tuple(float(r[s]) for s in skills), float(r["salary_k"]), float(r["automation_risk"]),
                float(r["base_demand"]), split_list(r["tags"]))
        for _, r in o.iterrows()
    )

    def boosts(r):
        return tuple((s, float(r[s])) for s in skills if s in r.index and pd.notna(r[s]) and float(r[s]) != 0)

    t = numeric_frame(clean("training", frames.get("training", pd.DataFrame())), list(skills) + ["duration_months"])
    training = tuple((str(r["name"]), boosts(r), max(1, int(r["duration_months"])) if pd.notna(r["duration_months"]) else 1) for _, r in t.iterrows()) if not t.empty else ()
    ts = numeric_frame(clean("tag_skills", frames.get("tag_skills", pd.DataFrame())), skills)
    tag_skills = tuple((str(r["key"]).strip().lower(), boosts(r)) for _, r in ts.iterrows()) if not ts.empty else ()
    students = ()
    st_df = numeric_frame(clean("students", frames.get("students", pd.DataFrame())), skills)
    if not st_df.empty:
        cols = [s for s in skills if s in st_df.columns]
        if cols:
            rows = []
            for _, r in st_df.iterrows():
                vec = tuple(float(np.clip(r[s], 0, 1)) if s in cols and pd.notna(r[s]) else 0.3 for s in skills)
                fav = as_text(r.get("favourite_occupation", ""))
                planned = parse_bool(r.get("planned", ""))
                rows.append((vec, fav, planned))
            students = tuple(rows)
    return MarketData(skills, occs, training, tag_skills, students, key=fingerprint(frames))


# ------------------------------------------------------- permanent defaults (admin)
def publish_defaults(frames: dict[str, pd.DataFrame]) -> str:
    """Make ``frames`` the data every new session starts with. The current files are
    backed up first; returns the backup folder name. Raises if the data has errors."""
    if has_errors(validate(frames)):
        raise ValueError("The data has validation errors")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dest = BACKUP_DIR / stamp
    dest.mkdir(parents=True, exist_ok=True)
    for key in SPECS:
        p = DATA_DIR / f"{key}.csv"
        if p.exists():
            shutil.copy2(p, dest / p.name)
    for key in SPECS:
        p = DATA_DIR / f"{key}.csv"
        df = frames.get(key, pd.DataFrame())
        if df is None or df.empty:
            if p.exists():
                p.unlink()  # an optional dataset that was cleared
        else:
            tmp = p.with_suffix(".tmp")
            df.to_csv(tmp, index=False)
            tmp.replace(p)
    return stamp


def list_backups() -> list[str]:
    if not BACKUP_DIR.exists():
        return []
    return sorted((d.name for d in BACKUP_DIR.iterdir() if d.is_dir()), reverse=True)


def restore_backup(name: str) -> str:
    """Restore a backup as the defaults (the current files are backed up first)."""
    src = BACKUP_DIR / Path(name).name  # no path traversal
    if not src.is_dir():
        raise FileNotFoundError(name)
    frames = {k: (normalise(pd.read_csv(src / f"{k}.csv")) if (src / f"{k}.csv").exists() else pd.DataFrame()) for k in SPECS}
    return publish_defaults(frames)
