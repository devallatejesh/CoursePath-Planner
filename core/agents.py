"""The four cooperating CoursePath agents plus the orchestrator.

    Student input -> Goal agent -> Constraint agent -> Planning agent -> Adaptation agent

Each agent owns one concern and returns an ``AgentStep`` so the UI can show
exactly what it did. All institutional data (catalog, requirements, careers,
seats) comes from the ``Catalog`` built from the active dataset bundle.

The Goal agent uses a deterministic keyword interpreter so the app runs
offline; it is the natural place to plug in a tool-calling LLM later.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace

from .catalog import Career, Catalog, Registrar

MAX_TERMS = 40  # hard stop for the search


# --------------------------------------------------------------------------- data
@dataclass
class AgentStep:
    agent: str
    action: str
    details: list[str] = field(default_factory=list)
    ok: bool = True


@dataclass
class Objective:
    career: Career
    interests: list[str]
    target_semesters: int
    max_credits: int
    start_season: str
    start_year: int
    completed: frozenset[str]
    avoid_hard: bool = False
    balance_load: bool = True
    excluded: frozenset[str] = frozenset()  # cancelled / unwanted courses

    @property
    def track(self) -> str:
        return self.career.track


@dataclass
class Semester:
    index: int
    label: str
    courses: list[str]
    history: bool = False  # already taken (fixed) vs planned
    note: str = ""
    credits: int = 0


@dataclass
class Plan:
    semesters: list[Semester]
    selected: set[str]
    unscheduled: set[str]
    rationale: dict[str, str]

    @property
    def future(self) -> list[Semester]:
        return [s for s in self.semesters if not s.history]

    @property
    def graduation(self) -> str | None:
        filled = [s for s in self.semesters if s.courses]
        if self.unscheduled or not filled:
            return None
        return filled[-1].label

    @property
    def term_count(self) -> int:
        filled = [s.index for s in self.semesters if s.courses]
        return (max(filled) + 1) if filled else 0

    def where(self) -> dict[str, str]:
        return {c: s.label for s in self.semesters for c in s.courses}


def _sem(cat: Catalog, index, label, courses, **kw) -> Semester:
    return Semester(index, label, courses, credits=sum(cat.courses[c].credits for c in courses), **kw)


# --------------------------------------------------------------------- Goal agent
SYNONYMS = {
    "ai": ("artificial intelligence", "machine learning", "neural", "llm", "robot"),
    "data": ("statistic", "analytics", "visuali"),
    "security": ("cyber", "hack", "crypt", "privacy"),
    "hci": ("ux", "design", "user experience", "interface", "psycholog"),
    "software": ("web", "app", "mobile", "coding", "developer"),
    "cloud": ("devops", "infrastructure", "aws", "kubernetes"),
    "systems": ("hardware", "embedded", "compiler", "operating"),
    "ethics": ("ethic", "responsible", "fairness", "society"),
    "business": ("startup", "econom", "management", "entrepreneur"),
}


class GoalAgent:
    name = "Goal agent"

    def __init__(self, catalog: Catalog):
        self.cat = catalog

    def interest_words(self) -> dict[str, tuple[str, ...]]:
        words = {}
        for tag in self.cat.interest_tags:
            w = {tag.lower()} | set(SYNONYMS.get(tag.lower(), ()))
            for c in self.cat.careers.values():
                if tag in c.tags:
                    w |= set(c.keywords)
            words[tag] = tuple(x for x in w if len(x) > 1)
        return words

    def interpret(self, text: str, form: dict) -> tuple[Objective, AgentStep]:
        t = (text or "").lower()
        notes: list[str] = []
        careers = self.cat.careers

        career = careers.get(form.get("career") or "")
        if career is None:
            def hits(c):
                return sum(bool(re.search(r"\b" + re.escape(k), t)) for k in c.keywords)
            best = max(careers.values(), key=hits)
            if hits(best) > 0:
                career = best
                notes.append(f"Career goal inferred from text: **{career.name}**")
            else:
                career = next(iter(careers.values()))
                notes.append(f"No career goal detected, defaulting to **{career.name}**")
        else:
            notes.append(f"Career goal: **{career.name}** (track `{career.track}`)")

        interests = list(dict.fromkeys(form.get("interests") or []))
        for tag, words in self.interest_words().items():
            if tag not in interests and any(re.search(r"\b" + re.escape(w), t) for w in words):
                interests.append(tag)
        interests = [i for i in interests if i in self.cat.interest_tags]
        notes.append("Interests: " + (", ".join(f"`{i}`" for i in interests) or "none stated"))

        per_year = len(self.cat.requirements.seasons)
        target = int(form.get("target_semesters") or 8)
        m = re.search(r"(\d+(?:\.\d+)?)\s*(years?|yrs?)", t)
        m2 = re.search(r"(\d+)\s*(semesters?|terms?)", t)
        if m2:
            target = int(m2.group(1))
            notes.append(f"Timeline from text: {target} terms")
        elif m:
            target = int(round(float(m.group(1)) * per_year))
            notes.append(f"Timeline from text: {m.group(1)} years = {target} terms")
        elif any(w in t for w in ("early", "fast", "asap", "accelerat")):
            target = max(1, target - 1)
            notes.append(f"Wants to graduate early: target reduced to {target} terms")
        else:
            notes.append(f"Target: {target} terms")

        max_credits = int(form.get("max_credits") or 15)
        if any(w in t for w in ("part-time", "part time", "light", "work while", "job while")):
            max_credits = min(max_credits, 12)
            notes.append("Lighter load requested: max 12 credits per term")
        elif any(w in t for w in ("heavy", "overload", "max load")):
            max_credits = max(max_credits, 18)
            notes.append("Heavy load requested: up to 18 credits per term")
        avoid_hard = bool(form.get("avoid_hard")) or any(w in t for w in ("avoid hard", "not too hard", "easier", "gpa"))
        if avoid_hard:
            notes.append(f"Will limit historically difficult courses to {self.cat.requirements.max_hard_if_avoiding} per term")

        seasons = self.cat.requirements.seasons
        obj = Objective(
            career=career,
            interests=interests,
            target_semesters=max(1, min(target, MAX_TERMS)),
            max_credits=max(1, min(max_credits, 30)),
            start_season=form.get("start_season") if form.get("start_season") in seasons else seasons[0],
            start_year=int(form.get("start_year", 2026)),
            completed=frozenset(c for c in (form.get("completed") or []) if c in self.cat.courses),
            avoid_hard=avoid_hard,
            balance_load=bool(form.get("balance_load", True)),
        )
        notes.append(f"{len(obj.completed)} course(s) already completed on transcript")
        return obj, AgentStep(self.name, "Interpreted goals into a structured objective", notes)


# --------------------------------------------------------------- Constraint agent
class ConstraintAgent:
    name = "Constraint agent"

    def __init__(self, catalog: Catalog, registrar: Registrar):
        self.cat = catalog
        self.registrar = registrar

    def max_hard(self, obj: Objective) -> int:
        r = self.cat.requirements
        return r.max_hard_if_avoiding if obj.avoid_hard else r.max_hard_per_term

    def earliest_terms(self, obj: Objective, done: set[str], start_index: int) -> dict[str, int]:
        """Earliest term each course could be taken with unlimited load."""
        memo: dict[str, int] = {}
        courses = self.cat.courses

        def first_offered(code: str, idx: int) -> int:
            for _ in range(len(self.cat.requirements.seasons) + 1):
                if self.cat.season_of(self.cat.term_label(obj.start_season, obj.start_year, idx)) in courses[code].terms:
                    return idx
                idx += 1
            return 10**6  # never offered

        def go(code: str) -> int:
            if code in done:
                return start_index - 1
            if code in memo:
                return memo[code]
            memo[code] = 10**6  # cycle guard
            after = max([go(p) for p in courses[code].prereqs if p in courses], default=start_index - 1) + 1
            memo[code] = first_offered(code, max(after, start_index))
            return memo[code]

        for c in courses:
            go(c)
        return memo

    def eligible(self, code: str, done: set[str], label: str, *, check_seats: bool, blocked: set[tuple[str, str]]) -> tuple[bool, str]:
        c = self.cat.courses[code]
        if self.cat.season_of(label) not in c.terms:
            return False, "not offered this season"
        missing = [p for p in c.prereqs if p not in done]
        if missing:
            return False, "missing " + ", ".join(missing)
        if (code, label) in blocked:
            return False, "section full"
        if (check_seats or (code, label) in self.registrar.overrides) and self.registrar.seats_open(code, label) <= 0:
            return False, "registrar reports 0 seats"
        return True, ""

    def validate(self, plan: Plan, obj: Objective) -> list[tuple[str, str]]:
        """Guardrail: independent re-check of every hard constraint."""
        cat, req = self.cat, self.cat.requirements
        issues: list[tuple[str, str]] = []
        done = set(obj.completed)
        seen: set[str] = set(obj.completed)
        for s in plan.semesters:
            term = set(s.courses)
            for code in s.courses:
                c = cat.courses[code]
                if code in seen:
                    issues.append(("error", f"{code} scheduled twice ({s.label})"))
                seen.add(code)
                if cat.season_of(s.label) not in c.terms:
                    issues.append(("error", f"{code} is not offered in {s.label.split()[0]}"))
                for p in c.prereqs:
                    if p not in done:
                        issues.append(("error", f"{code} in {s.label} before prerequisite {p}"))
                for q in c.coreqs:
                    if q not in done and q not in term:
                        issues.append(("error", f"{code} in {s.label} without co-requisite {q}"))
            if not s.history and s.credits > obj.max_credits:
                linked = len(s.courses) > 1 and all(set(cat.courses[c].coreqs) & term for c in s.courses)
                hint = " because its co-requisites must be taken together; raise the credit limit" if linked else ""
                issues.append(("error", f"{s.label} has {s.credits} credits (limit {obj.max_credits}){hint}"))
            hard = sum(cat.courses[c].hard for c in s.courses)
            if not s.history and hard > self.max_hard(obj):
                issues.append(("warning", f"{s.label} has {hard} historically difficult courses"))
            done |= term

        for code in sorted(cat.required - done):
            issues.append(("error", f"Degree audit: required course {code} never scheduled"))
        gen = [c for c in done if c in cat.geneds]
        if len(gen) < req.gened_choices:
            issues.append(("error", f"Degree audit: {len(gen)}/{req.gened_choices} gen-ed electives"))
        el = [c for c in done if c in cat.electives and cat.courses[c].counts]
        tr = [c for c in el if obj.track in cat.courses[c].tags]
        if len(tr) < req.track_electives:
            issues.append(("error", f"Degree audit: {len(tr)}/{req.track_electives} `{obj.track}` track electives"))
        if len(el) < req.track_electives + req.free_electives:
            issues.append(("error", f"Degree audit: {len(el)}/{req.track_electives + req.free_electives} electives"))
        if plan.unscheduled:
            issues.append(("error", "Could not place: " + ", ".join(sorted(plan.unscheduled))))
        if plan.term_count > obj.target_semesters:
            issues.append(("warning", f"Plan needs {plan.term_count} terms, target was {obj.target_semesters}"))
        return issues

    def report(self, obj: Objective, done: set[str], start_index: int) -> AgentStep:
        req = self.cat.required
        earliest = self.earliest_terms(obj, done, start_index)
        crit = max((earliest[c] for c in req - done), default=start_index - 1) - start_index + 1
        first = self.cat.term_label(obj.start_season, obj.start_year, start_index)
        full_now = [c for c, v in self.cat.courses.items() if c not in done and self.cat.season_of(first) in v.terms
                    and self.registrar.seats_open(c, first) <= 0]
        details = [
            f"{len(req - done)} required courses remain ({', '.join(self.cat.requirements.required_categories)} + named requirements)",
            f"Prerequisite + offering analysis: required courses need at least **{crit}** more term(s)",
            f"Credit limit {obj.max_credits}/term, max {self.max_hard(obj)} difficult course(s)/term",
            f"Registrar check for {first}: " + (", ".join(full_now) + " full" if full_now else "no full sections"),
        ]
        if self.cat.seat_overrides:
            details.append(f"Using {len(self.cat.seat_overrides)} uploaded registrar seat record(s)")
        ok = crit <= obj.target_semesters - start_index
        if not ok:
            details.append(f"Target of {obj.target_semesters} terms is not reachable; planning for earliest finish")
        return AgentStep(self.name, "Filtered valid options and checked feasibility", details, ok)


# ----------------------------------------------------------------- Planning agent
class PlanningAgent:
    name = "Planning agent"

    def __init__(self, catalog: Catalog, constraints: ConstraintAgent):
        self.cat = catalog
        self.constraints = constraints

    def _score(self, code: str, obj: Objective, keep: set[str] = frozenset()) -> float:
        c = self.cat.courses[code]
        s = 2.0 * (code in keep)  # stability: prefer what the student already planned
        s += 3.0 * (obj.track in c.tags)
        s += 1.0 * len(set(c.tags) & set(obj.career.tags))
        s += 1.2 * len(set(c.tags) & set(obj.interests))
        s += 2.0 * c.pass_rate
        if obj.avoid_hard and c.hard:
            s -= 1.5
        return s

    def choose(self, obj: Objective, done: set[str], start_index: int, keep: set[str] = frozenset()) -> tuple[set[str], dict[str, str]]:
        """Pick which gen-eds and electives satisfy the degree, guided by goals."""
        cat, req = self.cat, self.cat.requirements
        electives = [e for e in cat.electives if cat.courses[e].counts]
        rationale: dict[str, str] = {}
        sel = set(cat.required)
        for c in sel:
            rationale[c] = "Degree requirement"
        earliest = self.constraints.earliest_terms(obj, done, start_index)
        deadline = max(obj.target_semesters - 1, max((earliest[c] for c in sel if c not in done), default=0))

        def closure(code: str) -> list[str]:
            out: list[str] = []
            for p in cat.courses[code].prereqs:
                if p in electives and p not in done and p not in sel:
                    out += closure(p)
            return out + [code]

        relaxed = False

        def feasible(code: str) -> bool:
            return code not in obj.excluded and earliest.get(code, 10**6) < 10**6 and (relaxed or earliest.get(code, 99) <= deadline)

        have = [c for c in done if c in electives]
        track_have = sum(obj.track in cat.courses[c].tags for c in have)
        need_track = max(0, req.track_electives - track_have)
        need_total = max(0, req.track_electives + req.free_electives - len(have))
        need_total = max(need_total, need_track)  # after a goal change, extra track electives are needed
        picked: list[str] = []

        def take(chain: list[str], why) -> None:
            for x in chain:
                picked.append(x)
                rationale[x] = why(x)

        for relaxed in (False, True):  # second pass ignores the timeline if the track cannot be met in time
            pool = sorted((c for c in electives if c not in done and feasible(c)), key=lambda c: -self._score(c, obj, keep))
            for c in pool:
                if need_track <= 0:
                    break
                if obj.track in cat.courses[c].tags and c not in picked:
                    chain = [x for x in closure(c) if x not in picked]
                    if all(feasible(x) for x in chain):
                        take(chain, lambda x, c=c: f"Track elective for {obj.career.name}" if obj.track in cat.courses[x].tags else f"Prerequisite for {c}")
                        need_track -= sum(obj.track in cat.courses[x].tags for x in chain)
            if need_track <= 0:
                break
        relaxed = False
        for relaxed in (False, True):
            pool = sorted((c for c in electives if c not in done and feasible(c)), key=lambda c: -self._score(c, obj, keep))
            for c in pool:
                if len(picked) >= need_total:
                    break
                if c not in picked:
                    chain = [x for x in closure(c) if x not in picked]
                    if all(feasible(x) for x in chain) and len(picked) + len(chain) <= need_total:
                        def why(x):
                            tags = set(cat.courses[x].tags) & set(obj.interests)
                            return "Free elective" + (f" matching interest {', '.join(sorted(tags))}" if tags else " (high pass rate / career fit)")
                        take(chain, why)
            if len(picked) >= need_total:
                break
        sel |= set(picked)

        gen_have = sum(c in cat.geneds for c in done)
        gpool = sorted((g for g in cat.geneds if g not in done and g not in obj.excluded), key=lambda c: -self._score(c, obj, keep))
        for g in gpool[: max(0, req.gened_choices - gen_have)]:
            sel.add(g)
            rationale[g] = "Gen-ed elective" + (" (interest match)" if set(cat.courses[g].tags) & set(obj.interests) else "")

        # Close over prerequisites and co-requisites of everything selected (any category).
        stack = list(sel)
        while stack:
            c = stack.pop()
            for p in cat.courses[c].prereqs + cat.courses[c].coreqs:
                if p not in sel and p not in done and p in cat.courses:
                    sel.add(p)
                    rationale.setdefault(p, f"{'Co-requisite' if p in cat.courses[c].coreqs else 'Prerequisite'} of {c}")
                    stack.append(p)
        return sel - done, rationale

    def schedule(self, obj, selected, done, start_index, blocked, balance, anchors=None):
        cat = self.cat
        anchors = anchors or {}
        remaining = set(selected) - done
        done = set(done)
        dependents: dict[str, list[str]] = {c: [] for c in cat.courses}
        for c, v in cat.courses.items():
            for p in v.prereqs:
                dependents.setdefault(p, []).append(c)
        tail_memo: dict[str, int] = {}

        def tail(code: str) -> int:
            if code not in tail_memo:
                tail_memo[code] = 1 + max((tail(d) for d in dependents.get(code, []) if d in remaining), default=0)
            return tail_memo[code]

        req_cats = set(cat.requirements.required_categories)

        def cat_rank(c):
            v = cat.courses[c]
            return 0 if (v.category in req_cats or c in cat.required) else (1 if c in cat.electives else 2)

        max_hard = self.constraints.max_hard(obj)
        semesters: list[Semester] = []
        waiting: set[str] = set()  # oversized co-requisite groups that were skipped once: they go first next time
        idx = start_index
        while remaining and idx < start_index + MAX_TERMS:
            tail_memo.clear()
            label = cat.term_label(obj.start_season, obj.start_year, idx)
            first = idx == start_index
            cands = [c for c in remaining if self.constraints.eligible(c, done, label, check_seats=first, blocked=blocked)[0]]
            cands.sort(key=lambda c: (c not in waiting, -tail(c), anchors.get(c) != label, len(cat.courses[c].terms), cat_rank(c), c))

            cap = obj.max_credits
            if balance:
                terms_left = obj.target_semesters - idx
                rem_cr = sum(cat.courses[c].credits for c in remaining)
                if terms_left > 0:
                    cap = min(obj.max_credits, max(min(9, obj.max_credits), math.ceil(rem_cr / terms_left) + 1))

            chosen: list[str] = []
            credits = hard = 0
            for c in cands:
                if c in chosen:
                    continue
                group = [c] + [q for q in cat.courses[c].coreqs if q not in done and q not in chosen]
                if any(q not in remaining for q in group[1:]):
                    continue
                if any(not self.constraints.eligible(q, done, label, check_seats=first, blocked=blocked)[0] for q in group[1:]):
                    continue
                g_cr = sum(cat.courses[q].credits for q in group)
                g_hard = sum(cat.courses[q].hard for q in group)
                # A group that alone exceeds the term limits (e.g. two linked difficult courses when only
                # one is allowed) could otherwise never be placed: give it a term to itself and let the
                # guardrails report the breach.
                oversized = g_cr > cap or g_hard > max_hard
                if oversized:
                    if chosen:
                        waiting.update(group)
                        continue
                elif credits + g_cr > cap or hard + g_hard > max_hard:
                    continue
                chosen += group
                credits += g_cr
                hard += g_hard
                if oversized:
                    break  # term holds only this group
            note = "" if chosen else "No eligible courses this term (waiting on seasonal offering)"
            semesters.append(_sem(cat, idx, label, sorted(chosen, key=lambda c: (cat_rank(c), c)), note=note))
            done |= set(chosen)
            remaining -= set(chosen)
            idx += 1
        return semesters, remaining

    def plan(self, obj: Objective, history: list[Semester], blocked, previous: Plan | None = None) -> tuple[Plan, AgentStep]:
        done = set(obj.completed) | {c for s in history for c in s.courses}
        start_index = len(history)
        anchors = previous.where() if previous else {}
        selected, rationale = self.choose(obj, done, start_index, keep=set(anchors))
        sems, left = self.schedule(obj, selected, done, start_index, blocked, obj.balance_load, anchors)
        balanced = obj.balance_load
        if obj.balance_load and (left or start_index + len(sems) > obj.target_semesters):
            sems, left = self.schedule(obj, selected, done, start_index, blocked, False, anchors)
            balanced = False
        while sems and not sems[-1].courses:
            sems.pop()
        plan = Plan(history + sems, selected, left, rationale)
        details = [
            f"Selected {len(selected)} courses ({sum(self.cat.courses[c].credits for c in selected)} credits) to complete the degree",
            "Search: critical-path list scheduling (longest prerequisite chain first, rarely-offered courses prioritised)",
            "Load " + ("balanced across the target timeline" if balanced else "packed for earliest graduation"),
            f"Projected graduation: **{plan.graduation or 'not reachable'}** ({plan.term_count} terms)",
        ]
        return plan, AgentStep(self.name, "Built the term-by-term roadmap", details, ok=not left)


# --------------------------------------------------------------- Adaptation agent
@dataclass
class Event:
    kind: str  # dropped | full | cancelled | goal_change
    term_index: int
    course: str | None = None
    new_career: str | None = None


class AdaptationAgent:
    name = "Adaptation agent"

    def __init__(self, catalog: Catalog, planner: PlanningAgent, registrar: Registrar):
        self.cat = catalog
        self.planner = planner
        self.registrar = registrar

    def apply(self, obj: Objective, plan: Plan, ev: Event, blocked):
        cat = self.cat
        sems = {s.index: s for s in plan.semesters}
        label = sems[ev.term_index].label if ev.term_index in sems else cat.term_label(obj.start_season, obj.start_year, ev.term_index)
        details: list[str] = []

        def past(upto_inclusive: bool, drop: set[str] = frozenset()):
            out = []
            for s in plan.semesters:
                if s.index < ev.term_index or (upto_inclusive and s.index == ev.term_index):
                    courses = [c for c in s.courses if not (s.index == ev.term_index and c in drop)]
                    out.append(_sem(cat, s.index, s.label, courses, history=True))
            return out

        if ev.kind == "dropped":
            history = past(True, {ev.course} | set(cat.courses[ev.course].coreqs))
            details.append(f"{ev.course} dropped/failed in {label}; terms through {label} are now history")
        elif ev.kind == "full":
            self.registrar.mark_full(ev.course, label)
            blocked = blocked | {(ev.course, label)}
            history = past(False)
            details.append(f"Registrar: {ev.course} is full for {label}; re-planning from {label}")
        elif ev.kind == "cancelled":
            obj = replace(obj, excluded=obj.excluded | {ev.course})
            history = past(False)
            details.append(f"Catalog: {ev.course} cancelled from {label}; substitute course will be chosen")
        elif ev.kind == "goal_change":
            obj = replace(obj, career=cat.careers[ev.new_career])
            history = past(False)
            details.append(f"Goal changed to **{ev.new_career}** starting {label}")
        else:
            raise ValueError(ev.kind)

        new_plan, _ = self.planner.plan(obj, history, blocked, previous=plan)
        diff = self.diff(plan, new_plan)
        details += [
            f"Moved: {len(diff['moved'])}, added: {len(diff['added'])}, removed: {len(diff['removed'])}",
            f"Graduation: {plan.graduation} → **{new_plan.graduation or 'not reachable'}**",
        ]
        return obj, new_plan, AgentStep(self.name, "Re-planned the roadmap autonomously", details, ok=not new_plan.unscheduled), {**diff, "blocked": blocked}

    @staticmethod
    def diff(old: Plan, new: Plan) -> dict:
        a, b = old.where(), new.where()
        return {
            "moved": sorted((c, a[c], b[c]) for c in a.keys() & b.keys() if a[c] != b[c]),
            "added": sorted((c, b[c]) for c in b.keys() - a.keys()),
            "removed": sorted((c, a[c]) for c in a.keys() - b.keys()),
        }


# ------------------------------------------------------------------- orchestrator
class Orchestrator:
    """Sequences the hand-offs and keeps shared state (LangGraph/AutoGen role)."""

    def __init__(self, catalog: Catalog, seed: int = 7):
        self.cat = catalog
        self.registrar = Registrar(catalog, seed)
        self.goal = GoalAgent(catalog)
        self.constraint = ConstraintAgent(catalog, self.registrar)
        self.planner = PlanningAgent(catalog, self.constraint)
        self.adapter = AdaptationAgent(catalog, self.planner, self.registrar)

    def run(self, text: str, form: dict):
        obj, s1 = self.goal.interpret(text, form)
        s2 = self.constraint.report(obj, set(obj.completed), 0)
        plan, s3 = self.planner.plan(obj, [], set())
        issues = self.constraint.validate(plan, obj)
        return obj, plan, [s1, s2, s3, self._guardrail_step(issues)], issues

    def replan(self, obj: Objective, plan: Plan, ev: Event, blocked):
        obj, new_plan, step, diff = self.adapter.apply(obj, plan, ev, blocked)
        issues = self.constraint.validate(new_plan, obj)
        if any("track electives" in m for s, m in issues if s == "error"):
            step.ok = False
            step.details.append(
                f"Not enough `{obj.track}` electives remain reachable after this change. "
                "Options: an advisor substitution, restoring the course, or a different career goal."
            )
        return obj, new_plan, [step, self._guardrail_step(issues)], issues, diff

    @staticmethod
    def _guardrail_step(issues: list[tuple[str, str]]) -> AgentStep:
        errs = [m for s, m in issues if s == "error"]
        warns = [m for s, m in issues if s == "warning"]
        details = [f"{len(errs)} error(s), {len(warns)} warning(s)"] + errs[:5] + warns[:3]
        if not errs:
            details.append("Plan passes prerequisite, co-requisite, offering, credit-limit and degree-audit checks; ready for advisor review")
        return AgentStep("Guardrails", "Validated the plan before it reaches the student", details, ok=not errs)
