"""Site-wide settings that admins edit on the Admin page.

Stored in ``auth/settings.json`` next to the user accounts (git-ignored, because
it can hold the advisor invite code). Missing keys fall back to DEFAULTS.
"""

from __future__ import annotations

import json
import threading

from .auth import audit, auth_dir

_lock = threading.Lock()

DEFAULTS: dict = {
    # Branding and text
    "app_name": "CoursePath planner",
    "tagline": "Plan your degree with AI agents, get study resources for every subject, and test career paths.",
    "overview_intro": (
        "A team of cooperating agents interprets each student's goals, checks every constraint, "
        "and keeps the roadmap current all the way to graduation. A MESA agent-based model then "
        "tests how planned and unplanned career paths play out in a simulated job market."
    ),
    "welcome_message": (
        "In this app you can:\n"
        "- turn your goals into a term-by-term degree roadmap,\n"
        "- get study links under every subject,\n"
        "- re-plan when a course is dropped or your goal changes,\n"
        "- test career paths in a job-market simulation.\n\n"
        "The 10-minute tutorial walks you through it."
    ),
    "show_welcome": True,
    "announcement": "",
    "announcement_type": "info",  # info | success | warning | error
    # Access
    "allow_signup": True,
    "allow_guest": True,
    "advisor_code": "",  # empty = anyone may create an advisor account
    "max_attempts": 5,
    "lock_seconds": 30,
    # Who may change the session data on the Data manager page
    "data_manager_roles": ["student", "advisor", "admin"],
}

ANNOUNCEMENT_TYPES = ("info", "success", "warning", "error")


def settings_file():
    return auth_dir() / "settings.json"


def load() -> dict:
    out = dict(DEFAULTS)
    p = settings_file()
    if p.exists():
        try:
            stored = json.loads(p.read_text(encoding="utf-8"))
            out.update({k: v for k, v in stored.items() if k in DEFAULTS})
        except (OSError, json.JSONDecodeError):
            pass
    return out


def validate(new: dict) -> list[str]:
    problems = []
    if not str(new.get("app_name", "")).strip():
        problems.append("App name can't be empty.")
    if new.get("announcement_type") not in ANNOUNCEMENT_TYPES:
        problems.append("Unknown banner type.")
    if not 1 <= int(new.get("max_attempts", 0)) <= 50:
        problems.append("Failed sign-ins before lockout must be between 1 and 50.")
    if not 0 <= int(new.get("lock_seconds", -1)) <= 3600:
        problems.append("Lockout must be between 0 and 3600 seconds.")
    if "admin" not in new.get("data_manager_roles", []):
        problems.append("Admins must always be able to use the Data manager.")
    return problems


def save(new: dict, *, by: str) -> tuple[bool, str]:
    merged = {**load(), **{k: v for k, v in new.items() if k in DEFAULTS}}
    problems = validate(merged)
    if problems:
        return False, " ".join(problems)
    old = load()
    changed = sorted(k for k in DEFAULTS if merged.get(k) != old.get(k))
    if not changed:
        return True, "No changes."
    with _lock:
        p = settings_file()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        tmp.replace(p)
    audit(by, "edit settings", ", ".join("advisor_code" if k == "advisor_code" else k for k in changed))
    return True, "Settings saved: " + ", ".join(changed) + "."


def reset(*, by: str) -> None:
    p = settings_file()
    if p.exists():
        p.unlink()
    audit(by, "reset settings", "all settings back to defaults")
