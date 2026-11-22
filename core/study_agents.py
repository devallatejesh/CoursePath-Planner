"""Study agents for one semester.

Six cooperating agents turn a student's goal and time budget into a weekly
study plan, sharing a blackboard (``Blackboard``) and recording what they did
in a trace:

1. Profile agent   - reads the goal text, weeks and hours into a study profile
2. Syllabus agent  - breaks every subject's syllabus units into topics with effort
3. Priority agent  - ranks subjects and topics for the student's goal
4. Scheduler agent - spreads topics over the weeks within the hours budget
5. Resource agent  - attaches video and lecture links to every scheduled topic
6. Review agent    - checks the plan (overload, uncovered topics, revision time)

Everything is deterministic: the same inputs always give the same plan.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .curriculum import Subject, nptel_url, step_title, youtube_url
from .resources import recommended

# Goal keywords: a goal mentioning any trigger gains these focus keywords.
GOALS = {
    "AI / machine learning": (("ai", "artificial intelligence", "machine learning", "ml", "deep learning", "data science", "nlp"),
                              ("learning", "intelligence", "neural", "data", "probab", "statistic", "linear algebra",
                               "optimization", "vision", "language", "python", "reinforcement", "regression", "classification")),
    "Placements / coding interviews": (("placement", "interview", "job", "coding", "dsa", "leetcode", "product company"),
                                       ("data structure", "algorithm", "programming", "object oriented", "database",
                                        "operating system", "network", "sorting", "tree", "graph", "dynamic programming", "sql")),
    "GATE / competitive exams": (("gate", "ies", "ese", "psu", "competitive", "exam"),
                                 ("mathematics", "discrete", "algorithm", "theory of computation", "automata", "compiler",
                                  "digital", "signal", "network", "operating system", "control", "electromagnetic", "probability")),
    "Core electronics / VLSI": (("vlsi", "electronics", "embedded", "chip", "semiconductor", "circuit", "communication"),
                                ("vlsi", "circuit", "electronic", "digital", "analog", "embedded", "microcontroller",
                                 "signal", "communication", "semiconductor", "fpga", "wireless")),
    "Robotics / automation": (("robot", "drone", "automation", "mechatronics", "ros", "autonomous"),
                              ("robot", "kinematic", "dynamics", "control", "actuator", "sensor", "drone", "mechanism",
                               "embedded", "ros", "manufactur", "iot")),
    "Software development": (("software", "web", "app", "developer", "full stack", "cloud", "devops"),
                             ("software", "programming", "object oriented", "database", "web", "cloud", "distributed",
                              "user interface", "network", "security", "design")),
    "Research / higher studies": (("research", "ms ", "phd", "higher studies", "masters", "publication"),
                                  ("mathematics", "probability", "optimization", "theory", "research", "learning",
                                   "analysis", "algorithm", "linear algebra")),
    "Cyber security": (("security", "cyber", "hacking", "crypto", "forensic"),
                       ("security", "crypto", "network", "operating system", "forensic", "secure", "computer networks")),
}
DEFAULT_WEEKS = 16
TOPIC_HOURS = 2.0  # base hours to study one syllabus topic, scaled by subject weight


@dataclass
class Profile:
    goal_text: str
    goals: list[str]
    keywords: tuple[str, ...]
    weeks: int
    hours_per_week: float
    revision_weeks: int
    lab_hours: float


@dataclass
class Topic:
    subject: str  # subject title
    code: str
    step: int  # roadmap step (syllabus unit) number, 1-based
    step_name: str
    text: str
    hours: float
    priority: float = 1.0
    links: dict = field(default_factory=dict)


@dataclass
class Blackboard:
    subjects: list[Subject]
    profile: Profile | None = None
    topics: list[Topic] = field(default_factory=list)
    subject_scores: dict = field(default_factory=dict)  # title -> (score, reasons)
    weeks: list[list[Topic]] = field(default_factory=list)
    week_hours: list[float] = field(default_factory=list)
    issues: list[tuple[str, str]] = field(default_factory=list)
    trace: list[tuple[str, str, list[str]]] = field(default_factory=list)  # (agent, summary, details)
    general_outline: list[str] = field(default_factory=list)  # subjects planned from the general outline

    def log(self, agent: str, summary: str, details: list[str] | None = None):
        self.trace.append((agent, summary, details or []))


def split_topics(unit: str) -> list[str]:
    """Break one syllabus unit into study topics (short phrases)."""
    parts = re.split(r"\s[-–]\s|;\s*|\.\s+|,\s+(?=[A-Z])", unit)
    out, buf = [], ""
    for p in (x.strip(" .,;:-") for x in parts):
        if not p:
            continue
        buf = f"{buf}, {p}" if buf else p
        if len(buf) >= 25:
            out.append(buf)
            buf = ""
    if buf:
        if out and len(buf) < 25:
            out[-1] += ", " + buf
        else:
            out.append(buf)
    return out[:8] or [unit[:120]]


class ProfileAgent:
    name = "Profile agent"

    def run(self, bb: Blackboard, goal_text: str, weeks: int, hours_per_week: float, revision_weeks: int):
        text = f" {goal_text.lower()} "
        goals = [g for g, (triggers, _) in GOALS.items() if any(t in text for t in triggers)]
        free_words = tuple(w for w in re.findall(r"[a-z]{4,}", text) if w not in {"want", "become", "good", "like", "with", "this", "semester", "study", "learn", "focus", "prepare", "better", "marks"})
        keywords = tuple(dict.fromkeys(k for g in goals for k in GOALS[g][1])) + free_words
        weeks = max(4, min(int(weeks), 26))
        revision_weeks = max(0, min(int(revision_weeks), weeks // 3))
        labs = sum(1 for s in bb.subjects if s.kind == "Lab")
        lab_hours = 2.0 * labs  # lab prep each week, kept out of the topic budget
        bb.profile = Profile(goal_text.strip(), goals, keywords, weeks, float(hours_per_week), revision_weeks, lab_hours)
        bb.log(self.name, f"Goal: {', '.join(goals) or 'balanced (no specific goal detected)'} · {weeks} weeks · "
               f"{hours_per_week:g} h/week · {revision_weeks} revision week(s)",
               [f"Focus keywords: {', '.join(keywords[:12]) or 'none'}",
                f"{labs} lab course(s): {lab_hours:g} h/week reserved for lab preparation"])


class SyllabusAgent:
    name = "Syllabus agent"

    def run(self, bb: Blackboard):
        studied = [s for s in bb.subjects if s.kind == "Theory" and s.outline]
        general = [s.title for s in studied if not s.has_official_syllabus]
        for s in studied:
            weight = (s.credit_value or 3.0) / 3.0  # a 3-credit subject is the reference load
            for i, unit in enumerate(s.outline, 1):
                if s.has_official_syllabus:
                    for t in split_topics(unit):
                        bb.topics.append(Topic(s.title, s.code, i, step_title(unit), t, round(TOPIC_HOURS * weight, 1)))
                else:  # one general-outline step = one larger study block
                    bb.topics.append(Topic(s.title, s.code, i, step_title(unit), unit, round(TOPIC_HOURS * 2.5 * weight, 1)))
        bb.general_outline = general
        bb.log(self.name, f"Split {sum(len(s.outline) for s in studied)} roadmap steps of {len(studied)} subjects into "
               f"{len(bb.topics)} topics",
               [f"{s.title}: {sum(t.subject == s.title for t in bb.topics)} topics" for s in studied]
               + ([f"No official syllabus, so a general outline was used for: {', '.join(general)}"] if general else []))


class PriorityAgent:
    name = "Priority agent"

    def run(self, bb: Blackboard):
        p = bb.profile
        kws = [k for k in p.keywords if k]
        by_subject: dict[str, list[Topic]] = {}
        for t in bb.topics:
            by_subject.setdefault(t.subject, []).append(t)
        for title, topics in by_subject.items():
            blob = (title + " " + " ".join(t.text for t in topics)).lower()
            hits = [k for k in kws if k in blob]
            title_hits = [k for k in kws if k in title.lower()]
            score = 1.0 + 0.15 * len(hits) + 0.5 * len(title_hits)
            score = min(score, 3.0)
            reasons = (["title matches " + ", ".join(title_hits)] if title_hits else []) + \
                      (["syllabus mentions " + ", ".join(h for h in hits if h not in title_hits)[:80]] if len(hits) > len(title_hits) else [])
            bb.subject_scores[title] = (round(score, 2), reasons or ["core subject of the semester"])
            for t in topics:
                t.priority = round(score * (1.3 if any(k in t.text.lower() for k in kws) else 1.0), 2)
        ranked = sorted(bb.subject_scores.items(), key=lambda kv: -kv[1][0])
        bb.log(self.name, "Ranked subjects for the goal" if p.goals or p.keywords else "No goal given, so every subject gets equal priority",
               [f"{i}. {t} (score {s:.2f}): {'; '.join(r)}" for i, (t, (s, r)) in enumerate(ranked, 1)])


class SchedulerAgent:
    name = "Scheduler agent"

    def run(self, bb: Blackboard):
        p = bb.profile
        study_weeks = p.weeks - p.revision_weeks
        budget = max(1.0, p.hours_per_week - p.lab_hours)
        # Higher-priority topics get more time; total time is scaled to fit the budget when needed.
        for t in bb.topics:
            t.hours = round(t.hours * (0.75 + 0.25 * t.priority), 1)
        need = sum(t.hours for t in bb.topics)
        capacity = budget * study_weeks
        scale = min(1.0, capacity / need) if need else 1.0
        for t in bb.topics:
            t.hours = max(0.5, round(t.hours * scale * 2) / 2)
        # Interleave subjects week by week, keeping each subject's topics in syllabus order.
        queues = {}
        for t in bb.topics:
            queues.setdefault(t.subject, []).append(t)
        totals = {s: sum(t.hours for t in q) for s, q in queues.items()}
        done = dict.fromkeys(queues, 0.0)
        total_hours = sum(totals.values())
        # Spread the work evenly: each week gets an equal share of what is left (never more than the budget).
        bb.weeks = [[] for _ in range(study_weeks)]
        bb.week_hours = [0.0] * study_weeks
        for w in range(study_weeks):
            left_total = total_hours - sum(done.values())
            target = min(budget, left_total / (study_weeks - w)) if w < study_weeks - 1 else float("inf")
            hours = 0.0
            while True:
                ready = [s for s, q in queues.items() if q and (hours + q[0].hours <= target + 0.75 or not bb.weeks[w])]
                if not ready:
                    break
                # The subject furthest behind (relative to its size, favouring higher priority) goes next.
                s = min(ready, key=lambda x: (done[x] / totals[x]) / bb.subject_scores.get(x, (1.0, []))[0])
                t = queues[s].pop(0)
                bb.weeks[w].append(t)
                hours += t.hours
                done[s] += t.hours
            bb.week_hours[w] = round(hours, 1)
        bb.log(self.name, f"Scheduled {len(bb.topics)} topics over {study_weeks} study weeks + {p.revision_weeks} revision week(s)",
               [f"Topic budget: {budget:g} h/week after lab preparation",
                f"Needed {need:.0f} h, available {capacity:.0f} h" + (f", so topic time was scaled to {scale:.0%}" if scale < 1 else ""),
                f"Busiest week: {max(bb.week_hours or [0]):g} h, lightest: {min(bb.week_hours or [0]):g} h"])


class ResourceAgent:
    name = "Resource agent"

    def run(self, bb: Blackboard):
        own = {s.title: s.resources for s in bb.subjects if s.resources}  # the university's own picks
        for t in bb.topics:
            subject = re.sub(r"\(.*?\)", "", t.subject).strip()
            q = f"{subject} {t.text[:60]}"
            t.links = {"YouTube": youtube_url(q), "NPTEL": nptel_url(q)}
            for site, label, url in [x for x in recommended(t.subject) if x[0] != "YouTube"][:3]:
                t.links[f"{site} {label}"] = url  # e.g. Striver A2Z for DSA, W3Schools / GeeksforGeeks tutorials
            if own.get(t.subject):
                label, url = own[t.subject][0]
                t.links[label.split(":")[0].strip() + " course"] = url
        extra = sorted({k for t in bb.topics for k in t.links if k not in ("YouTube", "NPTEL")})
        bb.log(self.name, f"Attached YouTube and NPTEL links to {len(bb.topics)} topics",
               [f"Subject resources added: {', '.join(extra)}"] if extra else [])


class ReviewAgent:
    name = "Review agent"

    def run(self, bb: Blackboard):
        p = bb.profile
        scheduled = sum(len(w) for w in bb.weeks)
        if scheduled != len(bb.topics):
            bb.issues.append(("error", f"{len(bb.topics) - scheduled} topic(s) were not scheduled"))
        budget = max(1.0, p.hours_per_week - p.lab_hours)
        over = [i + 1 for i, h in enumerate(bb.week_hours) if h > budget * 1.25]
        if over:
            bb.issues.append(("warning", f"Week(s) {', '.join(map(str, over))} go over your topic budget of {budget:g} h"))
        if p.lab_hours >= p.hours_per_week:
            bb.issues.append(("warning", "Lab preparation uses all your hours. Increase hours per week."))
        need_per_week = sum(t.hours for t in bb.topics) / max(1, len(bb.weeks))
        if need_per_week > budget * 1.01:
            bb.issues.append(("warning", f"The syllabus needs about {need_per_week:.0f} h/week; you have {budget:g} h."))
        if p.revision_weeks == 0:
            bb.issues.append(("warning", "No revision weeks before exams. One or two are recommended."))
        if bb.general_outline:
            bb.issues.append(("info", "No official syllabus was published for " + ", ".join(bb.general_outline)
                              + ", so their weeks follow a general study outline. Swap in your class notes."))
        if not bb.topics:
            bb.issues.append(("error", "No subject in this semester has syllabus units to plan."))
        ok = not any(sev == "error" for sev, _ in bb.issues)
        bb.log(self.name, "Plan passed every check" if ok and not bb.issues else
               f"{'Plan is usable' if ok else 'Plan has problems'}: {len(bb.issues)} note(s)", [m for _, m in bb.issues])


def run_agents(subjects: list[Subject], goal_text: str = "", weeks: int = DEFAULT_WEEKS, hours_per_week: float = 20,
               revision_weeks: int = 2) -> Blackboard:
    """Run all six agents in order and return the shared blackboard."""
    bb = Blackboard(subjects)
    ProfileAgent().run(bb, goal_text, weeks, hours_per_week, revision_weeks)
    SyllabusAgent().run(bb)
    PriorityAgent().run(bb)
    SchedulerAgent().run(bb)
    ResourceAgent().run(bb)
    ReviewAgent().run(bb)
    return bb


def plan_rows(bb: Blackboard) -> list[dict]:
    rows = [dict(Week=w, Subject=t.subject, Code=t.code, Step=t.step, Topic=t.text, Hours=t.hours, Priority=t.priority)
            for w, topics in enumerate(bb.weeks, 1) for t in topics]
    n = len(bb.weeks)
    for r in range(bb.profile.revision_weeks if bb.profile else 0):
        rows.append(dict(Week=n + r + 1, Subject="All subjects", Code="", Step="", Topic="Revision and previous exam papers",
                         Hours=bb.profile.hours_per_week, Priority=""))
    return rows


AGENT_NAMES = [a.name for a in (ProfileAgent, SyllabusAgent, PriorityAgent, SchedulerAgent, ResourceAgent, ReviewAgent)]
