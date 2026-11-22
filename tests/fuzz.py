"""Randomised robustness test: random programs, random job markets, chains of re-plans.

Checks that nothing crashes and that the planner never breaks a hard rule
(prerequisite, co-requisite, offering season, duplicate, credit limit).

Run:  py tests/fuzz.py [n_programs]
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from core.abm import CareerPathModel, skills_from_courses  # noqa: E402
from core.agents import Event, Orchestrator  # noqa: E402
from core.datasets import build_catalog, build_market, has_errors, validate  # noqa: E402

HARD_RULES = ("before prerequisite", "without co-requisite", "is not offered", "scheduled twice", "credits (limit")
ALLOWED = "co-requisites must be taken together"  # genuinely impossible: linked courses exceed the student's limit


def random_frames(rng: random.Random) -> dict:
    seasons = rng.choice([["Fall", "Spring"], ["Fall", "Winter", "Spring"], ["Autumn", "Spring", "Summer"]])
    letters = "".join(s[0] for s in seasons)
    tags = ["t" + str(i) for i in range(rng.randint(2, 5))]
    n = rng.randint(12, 45)
    rows = []
    for i in range(n):
        code = f"C{i:03d}"
        k = rng.choice([0, 0, 1, 1, 2, 3])
        prereqs = rng.sample([r["code"] for r in rows], min(k, len(rows))) if rows else []
        terms = "".join(sorted(set(rng.sample(letters, rng.randint(1, len(letters)))), key=letters.index))
        cat = rng.choices(["core", "elective", "gened"], [4, 4, 2])[0]
        rows.append(dict(code=code, name=f"Course {i}", credits=rng.choice([1, 2, 3, 3, 4]), prereqs=";".join(prereqs), coreqs="",
                         terms=terms, category=cat, tags=";".join(rng.sample(tags, rng.randint(0, 2))),
                         pass_rate=round(rng.uniform(0.6, 0.99), 2), capacity=rng.randint(10, 80), counts=1))
    # a few co-requisite pairs sharing a season, with no prerequisites between them
    for _ in range(rng.randint(0, 2)):
        a, b = rng.sample(rows, 2)
        if a["code"] in b["prereqs"] or b["code"] in a["prereqs"] or a["coreqs"] or b["coreqs"]:
            continue
        a["coreqs"], b["coreqs"] = b["code"], a["code"]
        b["terms"] = a["terms"] = a["terms"][0]
        b["prereqs"] = a["prereqs"]
    courses = pd.DataFrame(rows)
    electives = courses[courses.category == "elective"]
    track_tags = [t for t in tags if sum(t in str(x).split(";") for x in electives.tags) >= 1] or tags[:1]
    req = pd.DataFrame([
        ("program", "Random"), ("required_categories", "core"), ("required_courses", ""),
        ("gened_category", "gened"), ("gened_choices", rng.randint(0, 2)), ("elective_category", "elective"),
        ("track_electives", rng.randint(0, 2)), ("free_electives", rng.randint(0, 2)), ("hard_threshold", 0.75),
        ("max_hard_per_term", rng.randint(1, 3)), ("max_hard_if_avoiding", 1), ("seasons", ";".join(seasons)),
        ("new_year_season", seasons[1]),
    ], columns=["key", "value"])
    careers = pd.DataFrame([dict(name=f"Career {t}", track=t, tags=t, median_salary_k=50, keywords=f"kw{t}") for t in track_tags])
    skills = [f"s{i}" for i in range(rng.randint(2, 7))]
    occ = pd.DataFrame([{"name": f"Job {j}", "salary_k": rng.randint(40, 150), "automation_risk": round(rng.random(), 2),
                         "base_demand": round(rng.uniform(0.3, 2), 2), "tags": rng.choice(tags),
                         **{s: round(rng.random(), 2) for s in skills}} for j in range(rng.randint(1, 8))])
    training = pd.DataFrame([{"name": f"Train {j}", "duration_months": rng.randint(1, 4), **{s: round(rng.random() * 0.3, 2) for s in skills}}
                             for j in range(rng.randint(0, 4))])
    tag_skills = pd.DataFrame([{"key": f"tag:{t}", **{s: round(rng.random() * 0.1, 2) for s in skills}} for t in tags])
    students = pd.DataFrame([{"favourite_occupation": rng.choice(list(occ.name) + [""]), "planned": rng.choice(["", 1, 0, "yes"]),
                              **{s: round(rng.random(), 2) for s in skills}} for _ in range(rng.randint(0, 30))])
    return {"courses": courses, "requirements": req, "careers": careers, "occupations": occ, "training": training,
            "tag_skills": tag_skills, "students": students, "seats": pd.DataFrame(), "literature": pd.DataFrame()}


def main(n_programs: int = 300):
    rng = random.Random(12345)
    stats = dict(programs=0, valid=0, plans=0, replans=0, audit_fail=0, sims=0)
    for i in range(n_programs):
        f = random_frames(rng)
        stats["programs"] += 1
        rep = validate(f)
        if has_errors(rep):
            continue
        stats["valid"] += 1
        cat, mk = build_catalog(f), build_market(f)
        for career in cat.careers:
            o = Orchestrator(cat, seed=i)
            form = dict(career=career, start_season=rng.choice(cat.requirements.seasons), start_year=2026,
                        max_credits=rng.choice([6, 9, 12, 15, 18]), avoid_hard=rng.random() < 0.3,
                        balance_load=rng.random() < 0.5, target_semesters=rng.randint(2, 12),
                        completed=rng.sample(list(cat.courses), rng.randint(0, 3)))
            obj, plan, _, issues = o.run(rng.choice(["", "part-time", "3 years", "graduate early", "kw" + career[-2:]]), form)
            stats["plans"] += 1
            hard = [m for s, m in issues if s == "error" and any(h in m for h in HARD_RULES) and ALLOWED not in m]
            assert not hard, (i, career, hard)
            if any(s == "error" for s, _ in issues):
                stats["audit_fail"] += 1
            blocked = set()
            for _ in range(4):  # chain of events, each on the latest plan
                future = [s for s in plan.semesters if not s.history and s.courses]
                if not future:
                    break
                term = rng.choice(future)
                kind = rng.choice(["dropped", "full", "cancelled", "goal_change"])
                optional = [c for s in future if s.index >= term.index for c in s.courses if c not in cat.required]
                if kind == "cancelled" and not optional:
                    kind = "dropped"
                ev = Event(kind, term.index,
                           course=rng.choice(optional) if kind == "cancelled" else rng.choice(term.courses),
                           new_career=rng.choice(list(cat.careers)))
                obj, plan, _, issues, diff = o.replan(obj, plan, ev, blocked)
                blocked = diff.pop("blocked")
                stats["replans"] += 1
                hard = [m for s, m in issues if s == "error" and any(h in m for h in HARD_RULES) and ALLOWED not in m]
                assert not hard, (i, career, ev, hard)
            if mk.tag_skills:
                skills_from_courses([c for s in plan.semesters for c in s.courses], cat, mk)
        m = CareerPathModel(mk, n_students=rng.randint(5, 60), use_uploaded_students=rng.random() < 0.5,
                            n_employers=rng.randint(1, 6), n_providers=rng.randint(0, 3), shock_step=rng.choice([None, 2]),
                            training_capacity=rng.randint(0, 10), rng=i)
        for _ in range(rng.randint(1, 8)):
            m.step()
        m.occupation_table()
        m.student_table()
        stats["sims"] += 1
    print(stats)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 300)
