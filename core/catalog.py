"""Planner data structures. Nothing is hard-coded here: a ``Catalog`` is built
from the active dataset bundle (see ``core/datasets.py``), which comes from
``data/*.csv`` by default or from files the user uploads."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from urllib.parse import quote_plus


@dataclass(frozen=True)
class Course:
    code: str
    name: str
    credits: int
    prereqs: tuple[str, ...] = ()
    coreqs: tuple[str, ...] = ()
    terms: str = "FS"  # letters of the seasons the course is offered in
    category: str = "elective"
    tags: tuple[str, ...] = ()
    pass_rate: float = 0.9
    capacity: int = 60
    counts: bool = True  # counts toward gen-ed / elective totals (labs usually don't)
    hard: bool = False  # pass rate below the program's difficulty threshold


@dataclass(frozen=True)
class Career:
    name: str
    track: str
    tags: tuple[str, ...]
    median_salary_k: float
    keywords: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class DegreeRequirements:
    program: str
    required_categories: tuple[str, ...]
    required_courses: tuple[str, ...]
    gened_category: str
    gened_choices: int
    elective_category: str
    track_electives: int
    free_electives: int
    hard_threshold: float
    max_hard_per_term: int
    max_hard_if_avoiding: int
    seasons: tuple[str, ...]
    new_year_season: str = "Spring"  # season in which the calendar year increments


@dataclass
class Catalog:
    courses: dict[str, Course]
    requirements: DegreeRequirements
    careers: dict[str, Career]
    seat_overrides: dict[tuple[str, str], int] = field(default_factory=dict)
    resources: dict[str, list[tuple[str, str, str]]] = field(default_factory=dict)  # code -> (title, url, type)
    resource_links: list[tuple[str, str, str]] = field(default_factory=list)  # (site name, url template, type)

    def resources_for(self, code: str) -> list[dict]:
        """Curated links for the course first, then a search link on every configured site."""
        out = [{"title": t, "url": u, "type": ty, "kind": "curated"} for t, u, ty in self.resources.get(code, [])]
        query = quote_plus(self.courses[code].name)
        out += [{"title": n, "url": tpl.replace("{query}", query), "type": ty, "kind": "search"} for n, tpl, ty in self.resource_links]
        return out

    @property
    def required(self) -> set[str]:
        r = self.requirements
        return {c for c, v in self.courses.items() if v.category in r.required_categories} | set(r.required_courses)

    @property
    def electives(self) -> list[str]:
        r = self.requirements
        return [c for c, v in self.courses.items() if v.category == r.elective_category and c not in self.required]

    @property
    def geneds(self) -> list[str]:
        """Gen-ed courses a student can choose (required ones and non-counting labs excluded)."""
        r = self.requirements
        return [c for c, v in self.courses.items() if v.category == r.gened_category and c not in self.required and v.counts]

    @property
    def interest_tags(self) -> list[str]:
        tags = {t for v in self.courses.values() for t in v.tags} | {t for c in self.careers.values() for t in c.tags}
        return sorted(tags)

    @property
    def categories(self) -> list[str]:
        return sorted({v.category for v in self.courses.values()})

    def term_label(self, start_season: str, start_year: int, index: int) -> str:
        seasons = list(self.requirements.seasons)
        k = seasons.index(start_season) if start_season in seasons else 0
        year = start_year
        for _ in range(index):
            k = (k + 1) % len(seasons)
            if seasons[k] == self.requirements.new_year_season:
                year += 1
        return f"{seasons[k]} {year}"

    @staticmethod
    def season_of(label: str) -> str:
        return label[0].upper()


class Registrar:
    """Seat availability. Uses uploaded seat data when present, otherwise a
    deterministic simulation from each course's capacity."""

    def __init__(self, catalog: Catalog, seed: int = 7):
        self.catalog = catalog
        self.seed = seed
        self.overrides: dict[tuple[str, str], int] = dict(catalog.seat_overrides)

    def seats_open(self, code: str, term_label: str) -> int:
        if (code, term_label) in self.overrides:
            return self.overrides[(code, term_label)]
        rng = random.Random(f"{self.seed}-{code}-{term_label}")
        cap = self.catalog.courses[code].capacity
        demand = rng.uniform(0.5, 1.04)
        return max(0, int(cap * (1 - demand)) + rng.randint(0, 4))

    def mark_full(self, code: str, term_label: str) -> None:
        self.overrides[(code, term_label)] = 0
