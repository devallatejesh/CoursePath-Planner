"""MESA agent-based model of career paths (slides 12-13 of the group deck).

Agents
    StudentAgent          job seeker with a skill vector, interests and a goal
    OccupationAgent       required skills, salary, automation risk, demand
    EmployerAgent         opens/closes vacancies, hires, lays off
    TrainingProviderAgent offers courses that raise specific skills
    AdvisorAgent          recommends the next best role + training (planned careers)

All skills, occupations, training courses and (optionally) the student
population come from ``MarketData``, built from the active dataset bundle.
One model step = one month. Default parameters are illustrative.
"""

from __future__ import annotations

import mesa
import networkx as nx
import numpy as np

from .datasets import MarketData


def match_score(skills: np.ndarray, req: np.ndarray) -> float:
    """Share of the required skill mass the worker covers (0-1)."""
    return float(np.minimum(skills, req).sum() / max(req.sum(), 1e-9))


def occupation_network(market: MarketData, threshold: float = 0.88) -> nx.Graph:
    g = nx.Graph()
    for o in market.occupations:
        g.add_node(o.name, salary=o.salary_k, risk=o.automation_risk)
    occs = list(market.occupations)
    for i, a in enumerate(occs):
        for b in occs[i + 1:]:
            va, vb = np.array(a.req), np.array(b.req)
            denom = np.linalg.norm(va) * np.linalg.norm(vb)
            sim = float(va @ vb / denom) if denom else 0.0
            if sim >= threshold:
                g.add_edge(a.name, b.name, weight=round(sim, 3))
    return g


def skills_from_courses(codes, catalog, market: MarketData, base: float = 0.15) -> np.ndarray:
    """Translate a roadmap into a skill vector using the tag/category mapping."""
    skills = list(market.skills)
    mapping = market.tag_skill_dict()
    v = np.full(len(skills), base)
    for code in codes:
        c = catalog.courses[code]
        keys = [f"tag:{t.lower()}" for t in c.tags] + [f"category:{c.category.lower()}"]
        for k in keys:
            for sk, d in mapping.get(k, {}).items():
                v[skills.index(sk)] += d
    return np.clip(v, 0, 1)


# ------------------------------------------------------------------------- agents
class OccupationAgent(mesa.Agent):
    def __init__(self, model, spec):
        super().__init__(model)
        self.spec = spec
        self.req = np.array(spec.req)
        self.demand = 1.0

    def step(self):
        m = self.model
        if m.shock_step is not None and m.steps == m.shock_step:
            self.demand *= 1 - m.shock_intensity * self.spec.automation_risk * 1.5
            if self.spec.automation_risk <= 0.15:  # automation-resistant roles grow
                self.demand *= 1 + 0.5 * m.shock_intensity
        self.demand = max(0.05, self.demand)


class EmployerAgent(mesa.Agent):
    def __init__(self, model, occupations):
        super().__init__(model)
        self.occupations = occupations
        self.vacancies = {o.spec.name: 0 for o in occupations}
        self.applicants = {o.spec.name: [] for o in occupations}

    def add_occupation(self, o):
        self.occupations.append(o)
        self.vacancies[o.spec.name] = 0
        self.applicants[o.spec.name] = []

    def open_vacancies(self):
        m = self.model
        for o in self.occupations:
            lam = o.spec.base_demand * o.demand * m.market_size / len(m.employers)
            self.vacancies[o.spec.name] += int(m.np_rng.poisson(max(lam, 0)))
            self.vacancies[o.spec.name] = int(self.vacancies[o.spec.name] * 0.85)  # postings expire

    def hire(self):
        m = self.model
        for o in self.occupations:
            name = o.spec.name
            pool = sorted(set(self.applicants[name]), key=lambda s: -match_score(s.skills, o.req))
            for s in pool:
                if self.vacancies[name] <= 0:
                    break
                if s.status == "searching" and match_score(s.skills, o.req) >= m.min_match:
                    s.get_hired(self, o)
                    self.vacancies[name] -= 1
            self.applicants[name] = []

    def layoffs(self):
        m = self.model
        if m.shock_step is None or m.steps < m.shock_step:
            return
        for s in m.students:
            if s.employer is self and s.occupation is not None:
                if m.random.random() < 0.02 * m.shock_intensity * s.occupation.spec.automation_risk:
                    s.lose_job()


class TrainingProviderAgent(mesa.Agent):
    def __init__(self, model, courses, capacity, efficiency):
        super().__init__(model)
        self.courses = courses
        self.capacity = capacity
        self.efficiency = efficiency
        self.enrolled = 0

    def has_seat(self) -> bool:
        return self.enrolled < self.capacity


class AdvisorAgent(mesa.Agent):
    """Recommends the best next role and the training that closes the biggest gap."""

    def advise(self, s):
        m = self.model
        total_vac = sum(sum(e.vacancies.values()) for e in m.employers) or 1
        best, best_score = None, -1.0
        for o in m.occupations:
            vac = sum(e.vacancies.get(o.spec.name, 0) for e in m.employers)
            score = 0.5 * match_score(s.skills, o.req) + 0.25 * s.interest[o.spec.name] + 0.25 * min(1.0, 5 * vac / total_vac)
            if score > best_score:
                best, best_score = o, score
        s.target = best
        gap = np.maximum(best.req - s.skills, 0)
        if m.training and match_score(s.skills, best.req) < m.min_match + 0.05 and gap.max() > 0.1:
            course = max(m.training, key=lambda c: sum(gap[m.skill_index[k]] * v for k, v in m.training[c][0].items()))
            s.enroll(course)


class StudentAgent(mesa.Agent):
    def __init__(self, model, skills, interest, planned, label=""):
        super().__init__(model)
        self.skills = skills
        self.interest = interest
        self.planned = planned
        self.label = label
        self.status = "searching"
        self.target = None
        self.employer = None
        self.occupation = None
        self.training = None
        self.first_job_step = None
        self.months_unemployed = 0
        self.failed_apps = 0
        self.courses_taken = 0

    def enroll(self, course: str) -> bool:
        providers = [p for p in self.model.providers if course in p.courses and p.has_seat()]
        if not providers:
            return False
        p = max(providers, key=lambda p: p.efficiency)
        p.enrolled += 1
        self.training = (course, self.model.training[course][1], p)
        self.status = "training"
        return True

    def get_hired(self, employer, occ):
        self.status, self.employer, self.occupation = "employed", employer, occ
        self.failed_apps = 0
        if self.first_job_step is None:
            self.first_job_step = self.model.steps

    def lose_job(self):
        self.status, self.employer, self.occupation, self.target = "searching", None, None, None

    def apply(self):
        m = self.model
        open_jobs = [(e, o) for e in m.employers for o in e.occupations if e.vacancies[o.spec.name] > 0]
        if not open_jobs:
            return
        if self.planned and self.target is not None:
            near = {self.target.spec.name} | set(m.network.neighbors(self.target.spec.name))
            options = [(e, o) for e, o in open_jobs if o.spec.name in near] or open_jobs
            options.sort(key=lambda eo: -match_score(self.skills, eo[1].req))
            picks = options[:3]
        else:
            w = np.array([0.2 + self.interest[o.spec.name] for _, o in open_jobs])
            idx = m.np_rng.choice(len(open_jobs), size=min(3, len(open_jobs)), replace=False, p=w / w.sum())
            picks = [open_jobs[i] for i in idx]
        for e, o in picks:
            e.applicants[o.spec.name].append(self)
        self.failed_apps += 1

    def step(self):
        m = self.model
        if self.status == "training":
            course, left, prov = self.training
            left -= 1
            if left <= 0:
                for k, v in m.training[course][0].items():
                    i = m.skill_index[k]
                    self.skills[i] = min(1.0, self.skills[i] + v * prov.efficiency)
                prov.enrolled -= 1
                self.training, self.status = None, "searching"
                self.courses_taken += 1
            else:
                self.training = (course, left, prov)
            return
        if self.status == "employed":
            self.skills += m.learning_rate * np.maximum(self.occupation.req - self.skills, 0)
            return
        self.months_unemployed += 1
        self.skills = np.maximum(self.skills - m.skill_decay, 0)
        if self.planned and (self.target is None or self.failed_apps >= 3):
            m.advisor.advise(self)
            self.failed_apps = 0
            if self.status == "training":
                return
        elif not self.planned and m.training and m.random.random() < 0.04:
            self.enroll(m.random.choice(list(m.training)))
            if self.status == "training":
                return
        self.apply()


# -------------------------------------------------------------------------- model
class CareerPathModel(mesa.Model):
    def __init__(
        self,
        market: MarketData,
        n_students: int = 300,
        advisor_coverage: float = 0.5,
        n_employers: int = 12,
        n_providers: int = 4,
        market_size: float = 9.0,
        min_match: float = 0.76,
        shock_step: int | None = 12,
        shock_intensity: float = 0.5,
        training_capacity: int = 25,
        learning_rate: float = 0.02,
        skill_decay: float = 0.003,
        network_threshold: float = 0.88,
        use_uploaded_students: bool = False,
        my_student_skills: tuple | None = None,
        my_student_clones: int = 0,
        rng: int | None = 42,
    ):
        super().__init__(rng=rng)
        self.np_rng = np.random.default_rng(rng)
        self.market_size = market_size
        self.min_match = min_match
        self.shock_step = shock_step if shock_step and shock_step > 0 else None
        self.shock_intensity = shock_intensity
        self.learning_rate = learning_rate
        self.skill_decay = skill_decay
        self.skill_index = {s: i for i, s in enumerate(market.skills)}
        self.training = market.training_dict()
        self.network = occupation_network(market, network_threshold)
        n_skills = len(market.skills)

        self.occupations = [OccupationAgent(self, spec) for spec in market.occupations]
        occ_by_name = {o.spec.name: o for o in self.occupations}
        self.employers = []
        for _ in range(max(1, n_employers)):
            k = self.random.randint(min(3, len(self.occupations)), min(5, len(self.occupations)))
            self.employers.append(EmployerAgent(self, self.random.sample(self.occupations, k)))
        for o in self.occupations:
            if not any(o in e.occupations for e in self.employers):
                self.random.choice(self.employers).add_occupation(o)
        names = list(self.training)
        self.providers = [
            TrainingProviderAgent(self, self.random.sample(names, min(4, len(names))), training_capacity, float(self.np_rng.uniform(0.7, 1.1)))
            for _ in range(n_providers)
        ] if names else []
        self.advisor = AdvisorAgent(self)

        def interests_for(fav):
            interest = {o.spec.name: float(self.np_rng.uniform(0, 0.4)) for o in self.occupations}
            if fav is not None:
                interest[fav.spec.name] = float(self.np_rng.uniform(0.7, 1.0))
                for nb in self.network.neighbors(fav.spec.name):
                    interest[nb] = max(interest[nb], 0.5)
            return interest

        self.students: list[StudentAgent] = []
        if use_uploaded_students and market.students:
            for vec, fav_name, planned in market.students:
                fav = occ_by_name.get(fav_name) or self.random.choice(self.occupations)
                is_planned = bool(planned >= 0.5) if planned is not None else self.random.random() < advisor_coverage
                self.students.append(StudentAgent(self, np.array(vec, float), interests_for(fav), is_planned))
        else:
            for _ in range(n_students):
                fav = self.random.choice(self.occupations)
                skills = np.clip(self.np_rng.beta(2.2, 3.0, n_skills) + 0.25 * fav.req * self.np_rng.uniform(0.5, 1.0), 0, 1)
                self.students.append(StudentAgent(self, skills, interests_for(fav), self.random.random() < advisor_coverage))
        if my_student_skills is not None:
            for _ in range(my_student_clones):
                self.students.append(StudentAgent(self, np.array(my_student_skills, float), interests_for(None), True, label="roadmap"))

        def rate(group):
            return (sum(s.status == "employed" for s in group) / len(group)) if group else None

        def avg(vals):
            vals = list(vals)
            return float(np.mean(vals)) if vals else None

        self.datacollector = mesa.DataCollector(
            model_reporters={
                "Employment rate": lambda m: rate(m.students),
                "Planned employment": lambda m: rate([s for s in m.students if s.planned and s.label != "roadmap"]),
                "Unplanned employment": lambda m: rate([s for s in m.students if not s.planned]),
                "Roadmap employment": lambda m: rate([s for s in m.students if s.label == "roadmap"]),
                "Skill match (employed)": lambda m: avg(match_score(s.skills, s.occupation.req) for s in m.students if s.status == "employed"),
                "Planned time to job": lambda m: avg(s.first_job_step for s in m.students if s.planned and s.first_job_step is not None),
                "Unplanned time to job": lambda m: avg(s.first_job_step for s in m.students if not s.planned and s.first_job_step is not None),
                "Open vacancies": lambda m: sum(sum(e.vacancies.values()) for e in m.employers),
                "In training": lambda m: sum(s.status == "training" for s in m.students),
                "Avg salary (k)": lambda m: avg(s.occupation.spec.salary_k for s in m.students if s.status == "employed"),
            }
        )
        self.running = True
        self.datacollector.collect(self)

    def step(self):
        for o in self.occupations:
            o.step()
        for e in self.employers:
            e.open_vacancies()
            e.layoffs()
        for s in self.random.sample(self.students, len(self.students)):
            s.step()
        for e in self.employers:
            e.hire()
        self.datacollector.collect(self)

    def occupation_table(self):
        return [{
            "Occupation": o.spec.name,
            "Workers": sum(s.occupation is o for s in self.students),
            "Open vacancies": sum(e.vacancies.get(o.spec.name, 0) for e in self.employers),
            "Demand multiplier": round(o.demand, 2),
            "Automation risk": o.spec.automation_risk,
            "Median salary (k)": o.spec.salary_k,
        } for o in self.occupations]

    def student_table(self):
        return [{
            "ID": s.unique_id,
            "Group": "Roadmap" if s.label == "roadmap" else ("Planned" if s.planned else "Unplanned"),
            "Status": s.status,
            "Occupation": s.occupation.spec.name if s.occupation else "",
            "Target": s.target.spec.name if s.target else "",
            "First job (month)": s.first_job_step,
            "Courses taken": s.courses_taken,
            "Skill match": round(match_score(s.skills, s.occupation.req), 2) if s.occupation else None,
        } for s in self.students]
