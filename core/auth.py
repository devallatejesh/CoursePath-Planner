"""Local user accounts, roles and the admin audit log.

Passwords are never stored: each user gets a random salt and a PBKDF2-SHA256
hash (200,000 iterations), compared in constant time. Accounts live in
``auth/users.json`` (git-ignored); set ``COURSEPATH_USERS_FILE`` to store them
elsewhere. The audit log and site settings sit in the same folder.

Roles
    student  build and explore roadmaps
    advisor  also approve roadmaps
    admin    everything, plus the Admin page (users, settings, permanent data)

Who becomes the first admin:
  * If ``COURSEPATH_ADMIN_USERNAME`` is set (environment variable, or a root-level
    secret on Streamlit Community Cloud), only an account with that username is made
    admin when it signs up, and only while no admin exists. Use this for any public
    deployment, so a stranger can't claim the admin role.
  * Otherwise the very first account created becomes ``admin`` (convenient locally).
Afterwards only admins can grant the admin role (Admin page, or
``py scripts/make_admin.py <username>``).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path

ITERATIONS = 200_000
ROLES = ("student", "advisor", "admin")
SIGNUP_ROLES = ("student", "advisor")  # admin can never be self-selected
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,31}$")
MIN_PASSWORD = 8
_lock = threading.RLock()


def users_file() -> Path:
    default = Path(__file__).resolve().parents[1] / "auth" / "users.json"
    return Path(os.environ.get("COURSEPATH_USERS_FILE", default))


def auth_dir() -> Path:
    return users_file().parent


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load() -> dict:
    p = users_file()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save(users: dict) -> None:
    p = users_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(users, indent=2), encoding="utf-8")
    tmp.replace(p)  # atomic on the same filesystem


def _hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS).hex()


def _set_password(rec: dict, password: str) -> None:
    salt = secrets.token_bytes(16)
    rec["salt"], rec["hash"] = salt.hex(), _hash(password, salt)


def reserved_admin() -> str | None:
    """Username reserved for the first administrator, if configured."""
    name = os.environ.get("COURSEPATH_ADMIN_USERNAME", "").strip().lower()
    return name or None


def normalise_username(username: str) -> str:
    return (username or "").strip().lower()


def password_problems(password: str, username: str = "") -> list[str]:
    problems = []
    if len(password) < MIN_PASSWORD:
        problems.append(f"at least {MIN_PASSWORD} characters")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        problems.append("at least one letter and one number")
    if username and username in password.lower():
        problems.append("must not contain your username")
    return problems


def public(username: str, rec: dict) -> dict:
    return {"username": username, "name": rec["name"], "role": rec["role"]}


# ------------------------------------------------------------------ accounts
def create_user(username: str, password: str, display_name: str, role: str = "student", *, by: str | None = None) -> tuple[bool, str]:
    """Create an account. Self sign-up (by=None) may only pick SIGNUP_ROLES, except that
    the very first account becomes admin."""
    username = normalise_username(username)
    if not USERNAME_RE.match(username):
        return False, "Username must be 3-32 characters: lowercase letters, numbers, dot, dash or underscore."
    if username == "guest":
        return False, "That username is reserved."
    if role not in ROLES or (by is None and role not in SIGNUP_ROLES):
        return False, "That role can't be chosen here."
    problems = password_problems(password, username)
    if problems:
        return False, "Password needs " + ", ".join(problems) + "."
    with _lock:
        users = _load()
        if username in users:
            return False, "That username is taken."
        reserved = reserved_admin()
        if reserved:
            first = username == reserved and admin_count(users) == 0
        else:
            first = not users
        if first:
            role = "admin"
        rec = {"name": (display_name or username).strip()[:60], "role": role, "created": now(), "last_login": None}
        _set_password(rec, password)
        users[username] = rec
        _save(users)
    audit(by or username, "create user", f"{username} as {role}" + (" (first administrator)" if first else ""))
    return True, "Account created" + (" (you are the administrator)" if first else "") + "."


def authenticate(username: str, password: str) -> dict | None:
    """Return the public user record, or None. Always does the same work to avoid timing leaks."""
    username = normalise_username(username)
    with _lock:
        users = _load()
        rec = users.get(username)
        salt = bytes.fromhex(rec["salt"]) if rec else b"\x00" * 16
        candidate = _hash(password or "", salt)
        if rec and hmac.compare_digest(candidate, rec["hash"]):
            rec["last_login"] = now()
            _save(users)
            return public(username, rec)
    return None


def get_user(username: str) -> dict | None:
    rec = _load().get(normalise_username(username))
    return public(normalise_username(username), rec) if rec else None


def list_users() -> list[dict]:
    return [{"username": u, "name": r["name"], "role": r["role"], "created": r.get("created"),
             "last_login": r.get("last_login")} for u, r in sorted(_load().items())]


def user_count() -> int:
    return len(_load())


def admin_count(users: dict | None = None) -> int:
    users = _load() if users is None else users
    return sum(r["role"] == "admin" for r in users.values())


def change_password(username: str, old: str, new: str) -> tuple[bool, str]:
    if not authenticate(username, old):
        return False, "Current password is wrong."
    problems = password_problems(new, username)
    if problems:
        return False, "New password needs " + ", ".join(problems) + "."
    with _lock:
        users = _load()
        _set_password(users[username], new)
        _save(users)
    audit(username, "change own password", "")
    return True, "Password changed."


# ------------------------------------------------------------- admin actions
def update_user(username: str, *, name: str | None = None, role: str | None = None, by: str) -> tuple[bool, str]:
    with _lock:
        users = _load()
        rec = users.get(username)
        if rec is None:
            return False, f"No user {username}."
        changes = []
        if role is not None and role != rec["role"]:
            if role not in ROLES:
                return False, f"Unknown role {role}."
            if rec["role"] == "admin" and admin_count(users) == 1:
                return False, "You can't remove the last administrator."
            changes.append(f"role {rec['role']} -> {role}")
            rec["role"] = role
        if name is not None and name.strip() and name.strip() != rec["name"]:
            changes.append(f"name -> {name.strip()[:60]}")
            rec["name"] = name.strip()[:60]
        if not changes:
            return True, "No changes."
        _save(users)
    audit(by, "edit user", f"{username}: " + ", ".join(changes))
    return True, f"Updated {username}."


def reset_password(username: str, new: str, *, by: str) -> tuple[bool, str]:
    problems = password_problems(new, username)
    if problems:
        return False, "Password needs " + ", ".join(problems) + "."
    with _lock:
        users = _load()
        if username not in users:
            return False, f"No user {username}."
        _set_password(users[username], new)
        _save(users)
    audit(by, "reset password", username)
    return True, f"Password for {username} was reset."


def delete_user(username: str, *, by: str) -> tuple[bool, str]:
    with _lock:
        users = _load()
        if username not in users:
            return False, f"No user {username}."
        if username == by:
            return False, "You can't delete your own account here."
        if users[username]["role"] == "admin" and admin_count(users) == 1:
            return False, "You can't delete the last administrator."
        del users[username]
        _save(users)
    audit(by, "delete user", username)
    return True, f"Deleted {username}."


def temporary_password() -> str:
    return secrets.token_urlsafe(9) + "7a"  # always has a letter and a digit


# --------------------------------------------------------------------- audit
def audit_file() -> Path:
    return auth_dir() / "audit.log"


def audit(actor: str, action: str, detail: str) -> None:
    p = audit_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    with _lock, p.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"time": now(), "user": actor, "action": action, "detail": detail}) + "\n")


def read_audit(limit: int = 500) -> list[dict]:
    p = audit_file()
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[::-1]
