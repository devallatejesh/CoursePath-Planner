"""Checks: planner validity, custom datasets, and that every page renders headlessly.

Run:  py tests/test_app.py   (or pytest if installed)
"""
import io
import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402

# Never touch the real accounts or data: use throw-away copies.
_TMP = Path(tempfile.mkdtemp())
os.environ["COURSEPATH_USERS_FILE"] = str(_TMP / "auth" / "users.json")
shutil.copytree(ROOT / "data", _TMP / "data", ignore=shutil.ignore_patterns("backups"))
os.environ["COURSEPATH_DATA_DIR"] = str(_TMP / "data")
# Ignore any real admin configured in .streamlit/secrets.toml (empty values win over secrets).
os.environ["COURSEPATH_ADMIN_USERNAME"] = ""
os.environ["COURSEPATH_ADMIN_PASSWORD_HASH"] = ""

import pandas as pd  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from core.abm import CareerPathModel  # noqa: E402
from core.agents import Event, Orchestrator  # noqa: E402
from core.datasets import (  # noqa: E402
    build_catalog, build_market, bundle_to_zip, frames_from_zip, has_errors, load_defaults, normalise, read_table, validate,
)

APP = str(ROOT / "streamlit_app.py")

from core import auth  # noqa: E402

STUDENT = {"username": "tester", "name": "Test Student", "role": "student"}
ADVISOR = {"username": "adv", "name": "Test Advisor", "role": "advisor"}


def new_app(user=STUDENT):
    """An AppTest already signed in (welcome dialog already shown)."""
    at = AppTest.from_file(APP, default_timeout=180)
    # Override the real .streamlit/secrets.toml so tests never seed the real admin.
    at.secrets["COURSEPATH_ADMIN_USERNAME"] = os.environ.get("COURSEPATH_ADMIN_USERNAME", "")
    at.secrets["COURSEPATH_ADMIN_PASSWORD_HASH"] = os.environ.get("COURSEPATH_ADMIN_PASSWORD_HASH", "")
    if user and user["username"] != "guest" and auth.get_user(user["username"]) is None:
        users = auth._load()  # make sure the account exists with exactly this role
        users[user["username"]] = {"name": user["name"], "role": user["role"], "salt": "00" * 16, "hash": "x", "created": auth.now()}
        auth._save(users)
    if user:
        at.session_state["user"] = user
        at.session_state["welcomed"] = True
    return at


def errors(issues):
    return [m for s, m in issues if s == "error"]


def test_default_data_valid():
    assert not has_errors(validate(load_defaults()))


def test_plans_and_replans_pass_guardrails():
    cat = build_catalog(load_defaults())
    for career, season, credits in itertools.product(cat.careers, cat.requirements.seasons, [12, 15, 18]):
        o = Orchestrator(cat)
        obj, plan, _, issues = o.run("", {"career": career, "start_season": season, "start_year": 2026, "max_credits": credits})
        assert not errors(issues), (career, issues)
        k = 2
        for ev in (Event("dropped", k, plan.semesters[k].courses[0]), Event("full", k, plan.semesters[k].courses[-1]),
                   Event("goal_change", k, new_career=list(cat.careers)[-1])):
            assert not errors(o.replan(obj, plan, ev, set())[3]), (career, ev)


def custom_frames():
    """A tiny, unrelated program (three terms per year, different categories and skills)."""
    f = {k: pd.DataFrame() for k in load_defaults()}
    f["courses"] = normalise(pd.DataFrame([
        ("BIO1", "Cells", 4, "", "", "FWS", "foundation", "lab", 0.9, 30, 1),
        ("BIO2", "Genetics", 4, "BIO1", "", "FW", "foundation", "genomics", 0.7, 30, 1),
        ("CHM1", "Chemistry", 4, "", "CHL1", "F", "foundation", "lab", 0.75, 30, 1),
        ("CHL1", "Chem lab", 1, "", "CHM1", "F", "foundation", "lab", 0.95, 20, 0),
        ("BIO3", "Bioinformatics", 4, "BIO2", "", "W", "option", "genomics;data", 0.8, 25, 1),
        ("BIO4", "Ecology", 4, "BIO1", "", "S", "option", "field", 0.9, 25, 1),
        ("BIO5", "Field methods", 4, "BIO4", "", "FS", "option", "field", 0.92, 25, 1),
        ("STA1", "Biostatistics", 4, "", "", "FWS", "option", "data;genomics", 0.85, 40, 1),
        ("HUM1", "Bioethics", 3, "", "", "FWS", "liberal", "ethics", 0.97, 50, 1),
        ("HUM2", "Science writing", 3, "", "", "FWS", "liberal", "", 0.97, 50, 1),
    ], columns=["code", "name", "credits", "prereqs", "coreqs", "terms", "category", "tags", "pass_rate", "capacity", "counts"]))
    f["requirements"] = pd.DataFrame([
        ("program", "B.Sc. Biology"), ("required_categories", "foundation"), ("required_courses", ""),
        ("gened_category", "liberal"), ("gened_choices", 1), ("elective_category", "option"),
        ("track_electives", 2), ("free_electives", 1), ("hard_threshold", 0.8), ("max_hard_per_term", 1),
        ("max_hard_if_avoiding", 1), ("seasons", "Fall;Winter;Spring"), ("new_year_season", "Winter"),
    ], columns=["key", "value"])
    f["careers"] = pd.DataFrame([("Genomics analyst", "genomics", "genomics;data", 90, "genomic;dna;bioinformatic"),
                                 ("Field ecologist", "field", "field", 60, "ecolog;field;conservation")],
                                columns=["name", "track", "tags", "median_salary_k", "keywords"])
    f["occupations"] = pd.DataFrame([("Genomics analyst", 90, 0.2, 1.0, "genomics", 0.8, 0.7, 0.3),
                                     ("Field ecologist", 60, 0.1, 0.8, "field", 0.3, 0.4, 0.9),
                                     ("Lab technician", 50, 0.6, 1.2, "lab", 0.4, 0.3, 0.3)],
                                    columns=["name", "salary_k", "automation_risk", "base_demand", "tags", "wetlab", "coding", "fieldwork"])
    f["training"] = pd.DataFrame([("Python for biologists", 2, 0, 0.3, 0), ("Field course", 1, 0, 0, 0.3)],
                                 columns=["name", "duration_months", "wetlab", "coding", "fieldwork"])
    f["tag_skills"] = pd.DataFrame([("tag:genomics", 0.1, 0.1, 0), ("tag:field", 0, 0, 0.15), ("tag:lab", 0.15, 0, 0)],
                                   columns=["key", "wetlab", "coding", "fieldwork"])
    f["students"] = pd.DataFrame([("A", "Field ecologist", 1, 0.3, 0.2, 0.8), ("B", "", "", 0.7, 0.6, 0.2)],
                                 columns=["student_id", "favourite_occupation", "planned", "wetlab", "coding", "fieldwork"])
    return f


def test_custom_dataset_end_to_end():
    f = custom_frames()
    rep = validate(f)
    assert not has_errors(rep), rep
    cat = build_catalog(f)
    assert cat.term_label("Fall", 2026, 1) == "Winter 2027"
    for career in cat.careers:
        o = Orchestrator(cat)
        obj, plan, _, issues = o.run("I love dna", {"career": career, "start_season": "Fall", "start_year": 2026, "max_credits": 12})
        assert not errors(issues), (career, issues)
    obj, plan, steps, _ = Orchestrator(cat).run("I want to work in conservation", {})
    assert obj.career.name == "Field ecologist"
    mk = build_market(f)
    m = CareerPathModel(mk, use_uploaded_students=True, rng=1)
    for _ in range(6):
        m.step()
    assert len(m.students) == 2


def test_validation_catches_bad_data():
    f = custom_frames()
    f["courses"].loc[0, "prereqs"] = "BIO2"  # BIO1 <-> BIO2 cycle
    f["courses"].loc[1, "pass_rate"] = 1.7
    msgs = " ".join(m for v in validate(f).values() for _, m in v)
    assert "cycle" in msgs and "pass_rate" in msgs


def test_upload_formats_roundtrip():
    f = custom_frames()
    z = frames_from_zip(bundle_to_zip(f))[0]
    assert set(z) >= {"courses", "occupations"} and len(z["courses"]) == len(f["courses"])
    buf = io.BytesIO()
    f["courses"].to_excel(buf, index=False)
    assert len(read_table("c.xlsx", buf.getvalue())) == len(f["courses"])
    semi = f["careers"].to_csv(index=False, sep=";").encode()
    assert list(read_table("c.csv", semi).columns)[:2] == ["name", "track"]


def _page(path, at=None, user=STUDENT):
    at = at or new_app(user)
    at.run()
    at.switch_page(path).run()
    assert not at.exception, at.exception
    return at


def test_pages_render():
    for p in ["app_pages/overview.py", "app_pages/simulation.py", "app_pages/literature.py", "app_pages/experiments.py", "app_pages/data.py"]:
        _page(p)


def test_planner_flow():
    at = _page("app_pages/planner.py")
    at.button[0].click().run()
    assert not at.exception, at.exception
    assert any("Projected graduation" in m.label for m in at.metric)
    [b for b in at.button if b.label == "Re-plan"][0].click().run()
    assert not at.exception, at.exception
    assert len(at.session_state["versions"]) == 2


def test_app_runs_on_custom_data():
    at = new_app()
    at.run()
    from core.datasets import fingerprint
    f = custom_frames()
    at.session_state["frames"] = f
    at.session_state["catalog"] = build_catalog(f)
    at.session_state["market"] = build_market(f)
    at.session_state["data_key"] = fingerprint(f)
    at.session_state["data_is_default"] = False
    for p in ["app_pages/overview.py", "app_pages/planner.py", "app_pages/simulation.py", "app_pages/data.py"]:
        at.switch_page(p).run()
        assert not at.exception, (p, at.exception)
    at.switch_page("app_pages/planner.py").run()
    at.button[0].click().run()
    assert not at.exception, at.exception


def test_experiments_batch():
    at = _page("app_pages/experiments.py")
    at.button[0].click().run()
    assert not at.exception, at.exception
    assert len(at.dataframe) >= 1


def test_planner_every_event_and_approval():
    at = _page("app_pages/planner.py")
    at.button[0].click().run()
    for kind in ["Section is full", "Course cancelled", "Goal changed", "Dropped / failed a course"]:
        [w for w in at.segmented_control if w.label == "Event"][0].set_value(kind).run()
        [b for b in at.button if b.label == "Re-plan"][0].click().run()
        assert not at.exception, (kind, at.exception)
        assert kind in at.session_state["trace"][-1][0], at.session_state["trace"][-1][0]
    assert len(at.session_state["versions"]) == 5
    errors_now = [m for s, m in at.session_state["issues"] if s == "error"]
    assert not [b for b in at.button if b.label == "Approve as advisor"], "students must not see the approve button"


def test_simulation_with_uploaded_students_and_roadmap():
    at = new_app()
    at.run()
    f = load_defaults()
    f["students"] = normalise(pd.read_csv(_TMP / "data" / "samples" / "students_sample.csv"))
    from core.datasets import fingerprint
    at.session_state["frames"] = f
    at.session_state["catalog"] = build_catalog(f)
    at.session_state["market"] = build_market(f)
    at.session_state["data_key"] = fingerprint(f)
    at.switch_page("app_pages/planner.py").run()
    at.button[0].click().run()
    assert at.session_state["roadmap_skills"] is not None
    at.switch_page("app_pages/simulation.py").run()
    assert not at.exception, at.exception
    labels = [t.label for t in at.toggle]
    assert any("uploaded students" in l for l in labels) and any("roadmap graduate" in l for l in labels)
    assert any("roadmap graduates" in m.label for m in at.metric)


def test_experiments_other_parameters():
    at = _page("app_pages/experiments.py")
    at.selectbox[0].set_value("min_match").run()
    at.selectbox[1].set_value("training_capacity").run()
    assert not at.exception, at.exception
    at.button[0].click().run()
    assert not at.exception, at.exception
    assert len(at.dataframe) >= 1


def test_data_manager_actions():
    at = _page("app_pages/data.py")
    for i, key in enumerate(["courses", "requirements", "careers", "occupations", "training", "tag_skills", "students", "seats", "literature"]):
        at.selectbox(key="dataset_choice").set_value(key).run()
        assert not at.exception, (key, at.exception)
    at.selectbox(key="dataset_choice").set_value("students").run()
    [b for b in at.button if b.label == "Start from template"][0].click().run()
    assert len(at.session_state["draft"]["students"]) > 0
    [b for b in at.button if b.label == "Apply to the whole app"][0].click().run()
    assert not at.exception, at.exception
    assert len(at.session_state["market"].students) > 0 and not at.session_state["data_is_default"]
    [b for b in at.button if b.label == "Clear"][0].click().run()
    [b for b in at.button if b.label == "Apply to the whole app"][0].click().run()
    assert len(at.session_state["market"].students) == 0
    [b for b in at.button if b.label == "Reset to defaults"][0].click().run()
    assert not at.exception, at.exception
    assert at.session_state["data_is_default"]


def test_bad_upload_is_blocked():
    at = _page("app_pages/data.py")
    bad = at.session_state["draft"]["courses"].copy()
    bad.loc[0, "prereqs"] = "NOPE"
    at.session_state["base"]["courses"] = bad
    at.session_state["draft"]["courses"] = bad
    at.session_state["draft_ver"]["courses"] += 1
    at.run()
    apply_btn = [b for b in at.button if b.label == "Apply to the whole app"][0]
    assert apply_btn.disabled
    assert any("unknown prereq NOPE" in e.value for e in at.error)


def test_resources_dataset():
    f = load_defaults()
    cat = build_catalog(f)
    assert all(cat.resources.get(c) for c in cat.courses), "every default course has a curated link"
    links = cat.resources_for("CS102")
    assert links[0]["kind"] == "curated" and any("Data+Structures" in r["url"] for r in links if r["kind"] == "search")
    bad = dict(f)
    bad["resources"] = pd.DataFrame({"code": ["CS101", "ZZ9"], "url": ["ftp://x", "https://example.org/a"]})
    bad["resource_links"] = pd.DataFrame({"name": ["Site"], "url_template": ["https://example.org/search"]})
    rep = validate(bad)
    msgs = " ".join(m for v in rep.values() for _, m in v)
    assert "must start with http" in msgs and "unknown course codes" in msgs and "{query}" in msgs
    none = dict(f)
    none["resources"], none["resource_links"] = pd.DataFrame(), pd.DataFrame()
    assert not has_errors(validate(none)) and build_catalog(none).resources_for("CS101") == []


def test_planner_shows_resources():
    at = _page("app_pages/planner.py")
    at.button[0].click().run()
    assert not at.exception, at.exception
    md = " ".join(m.value for m in at.markdown)
    assert "en.wikipedia.org/wiki/" in md and "ocw.mit.edu/search" in md and "youtube.com/results" in md
    at.toggle(key="show_resources").set_value(False).run()
    assert not at.exception, at.exception


def test_accounts():
    ok, msg = auth.create_user("alice", "short", "Alice")
    assert not ok and "8 characters" in msg
    ok, msg = auth.create_user("Bad Name!", "Passw0rd123", "x")
    assert not ok
    assert auth.create_user("alice", "Garden2024!", "Alice", "advisor")[0]
    assert not auth.create_user("ALICE", "Garden2024!", "Alice")[0], "usernames are case-insensitive and unique"
    assert auth.authenticate("Alice", "Garden2024!")["role"] == "advisor"
    assert auth.authenticate("alice", "wrong-pass1") is None and auth.authenticate("nobody", "x") is None
    raw = auth.users_file().read_text()
    assert "Garden2024!" not in raw and "hash" in raw, "passwords must be stored hashed"
    assert auth.change_password("alice", "Garden2024!", "Orchard2025!")[0]
    assert auth.authenticate("alice", "Orchard2025!") and not auth.authenticate("alice", "Garden2024!")


def test_login_gate_and_flow():
    at = new_app(user=None)
    at.run()
    assert not at.exception, at.exception
    assert any(b.label == "Continue as guest" for b in at.button)
    assert "user" not in at.session_state, "app content must not load before sign-in"
    # create an account through the form
    at.text_input[2].input("Bob Builder")
    at.text_input[3].input("bob")
    at.text_input[4].input("Builder123")
    at.text_input[5].input("Builder123")
    [b for b in at.button if b.label == "Create account"][0].click().run()
    assert not at.exception, at.exception
    assert at.session_state["user"]["username"] == "bob"
    # log out from the Account page
    at.switch_page("app_pages/account.py").run()
    [b for b in at.button if b.label == "Log out"][0].click().run()
    assert "user" not in at.session_state
    # wrong password, then right password
    at.text_input[0].input("bob")
    at.text_input[1].input("nope-nope1")
    [b for b in at.button if b.label == "Sign in"][0].click().run()
    assert "user" not in at.session_state and any("incorrect" in e.value for e in at.error)
    at.text_input[1].input("Builder123")
    [b for b in at.button if b.label == "Sign in"][0].click().run()
    assert at.session_state["user"]["name"] == "Bob Builder"


def test_lockout_after_failures():
    at = new_app(user=None)
    at.run()
    for _ in range(5):
        at.text_input[0].input("ghost")
        at.text_input[1].input("wrong-pass1")
        [b for b in at.button if b.label == "Sign in"][0].click().run()
    assert [b for b in at.button if b.label == "Sign in"][0].disabled


def test_guest_and_welcome_dialog():
    at = new_app(user=None)
    at.run()
    [b for b in at.button if b.label == "Continue as guest"][0].click().run()
    assert not at.exception, at.exception
    assert at.session_state["user"]["role"] == "student" and at.session_state["welcomed"]


def test_advisor_can_approve():
    at = _page("app_pages/planner.py", user=ADVISOR)
    at.button[0].click().run()
    [b for b in at.button if b.label == "Approve as advisor"][0].click().run()
    assert at.session_state["approved"] == "Test Advisor"


def test_tutorial_prefills_planner():
    at = _page("app_pages/tutorial.py")
    [b for b in at.button if b.label == "Try this"][1].click().run()
    assert not at.exception, at.exception
    assert "part-time" in at.text_area(key="goal_text").value
    at.switch_page("app_pages/planner.py")  # AppTest re-runs its own current page, so follow the app's switch
    at.button[0].click().run()  # Generate roadmap
    assert not at.exception, at.exception
    assert at.session_state["objective"].max_credits == 12, "tutorial example asked for part-time"


def _reset_accounts():
    for p in (_TMP / "auth").glob("*"):
        p.unlink()


def test_first_account_is_admin_and_admin_rules():
    _reset_accounts()
    assert auth.create_user("root", "Maple2024a", "Root")[0]
    assert auth.get_user("root")["role"] == "admin", "first account becomes admin"
    ok, _ = auth.create_user("eve", "Cedar2024b", "Eve", "admin")
    assert not ok, "self sign-up can't choose admin"
    assert auth.create_user("eve", "Cedar2024b", "Eve")[0] and auth.get_user("eve")["role"] == "student"
    assert not auth.update_user("root", role="student", by="root")[0], "can't demote the last admin"
    assert not auth.delete_user("root", by="root")[0], "can't delete yourself"
    assert auth.update_user("eve", role="admin", name="Eve A", by="root")[0]
    assert auth.update_user("root", role="advisor", by="eve")[0], "allowed once another admin exists"
    temp = auth.temporary_password()
    assert auth.reset_password("root", temp, by="eve")[0] and auth.authenticate("root", temp)
    assert auth.delete_user("root", by="eve")[0] and auth.get_user("root") is None
    actions = {r["action"] for r in auth.read_audit()}
    assert {"create user", "edit user", "reset password", "delete user"} <= actions


def test_admin_page_access_control():
    _reset_accounts()
    auth.create_user("boss", "Birch2024c", "Boss")  # admin
    auth.create_user("stu", "Aspen2024d", "Stu")
    def admin_reachable(at):
        try:
            at.switch_page("app_pages/admin.py")
            return True
        except ValueError:  # the page isn't registered in this user's navigation at all
            return False

    at = new_app(user=auth.get_user("stu"))
    at.run()
    assert not admin_reachable(at), "students must not be able to open the Admin page"
    # a forged role in the session is not enough: the stored role is checked on every run
    at = new_app(user={"username": "stu", "name": "Stu", "role": "admin"})
    at.run()
    assert at.session_state["user"]["role"] == "student", "role is refreshed from the account store"
    assert not admin_reachable(at)
    # an admin who is demoted loses access on the next interaction
    auth.create_user("temp-admin", "Spruce2024f", "Temp", "admin", by="boss")
    at = new_app(user=auth.get_user("temp-admin"))
    at.run()
    assert admin_reachable(at)
    auth.update_user("temp-admin", role="student", by="boss")
    at.run()
    assert not admin_reachable(at)
    # the real admin gets in
    at = new_app(user=auth.get_user("boss"))
    at.switch_page("app_pages/admin.py").run()
    assert not at.exception and not at.error, (at.exception, [e.value for e in at.error])
    assert at.title[0].value == "Admin"


def test_admin_edits_users_and_settings():
    _reset_accounts()
    auth.create_user("boss", "Birch2024c", "Boss")
    auth.create_user("stu", "Aspen2024d", "Stu")
    at = new_app(user=auth.get_user("boss"))
    at.switch_page("app_pages/admin.py").run()
    # create a user from the admin form
    at.text_input[0].input("New Advisor")
    at.text_input[1].input("newadv")
    at.selectbox[0].set_value("advisor")
    at.text_input[2].input("Larch2024e")
    [b for b in at.button if b.label == "Create user"][0].click().run()
    assert not at.exception, at.exception
    assert auth.get_user("newadv")["role"] == "advisor"
    # reset a password
    at.selectbox(key="reset_user").set_value("stu").run()
    [b for b in at.button if b.label == "Generate a temporary password"][0].click().run()
    temp = at.session_state["last_temp"][1]
    assert auth.authenticate("stu", temp)
    # delete a user
    at.selectbox(key="del_user").set_value("newadv").run()
    at.checkbox(key="del_sure").check().run()
    [b for b in at.button if b.label == "Delete user"][0].click().run()
    assert auth.get_user("newadv") is None
    # site settings: rename the app, add a banner, turn off guests
    at.text_input[at.text_input.values.index("CoursePath planner")].input("Uni Planner")
    banner = [t for t in at.text_input if t.label == "Banner text"][0]
    banner.input("Registration closes Friday")
    [t for t in at.toggle if t.label == "Allow guest access"][0].set_value(False)
    [b for b in at.button if b.label == "Save settings"][0].click().run()
    assert not at.exception, at.exception
    from core import settings
    cfg = settings.load()
    assert cfg["app_name"] == "Uni Planner" and cfg["announcement"] and not cfg["allow_guest"]
    at.switch_page("app_pages/overview.py").run()
    assert at.title[0].value == "Uni Planner"
    assert any("Registration closes Friday" in i.value for i in at.info)
    login = new_app(user=None)
    login.run()
    assert not any(b.label == "Continue as guest" for b in login.button)
    settings.reset(by="test")


def test_admin_publishes_and_restores_data():
    _reset_accounts()
    auth.create_user("boss", "Birch2024c", "Boss")
    from core.datasets import load_defaults, list_backups
    before = load_defaults()["careers"]
    at = new_app(user=auth.get_user("boss"))
    at.run()
    f = {k: v.copy() for k, v in at.session_state["frames"].items()}
    f["careers"].loc[0, "name"] = "Robotics Engineer"
    from core.datasets import fingerprint
    at.session_state["frames"] = f
    at.session_state["catalog"] = build_catalog(f)
    at.session_state["market"] = build_market(f)
    at.session_state["data_key"] = fingerprint(f)
    at.switch_page("app_pages/admin.py").run()
    at.checkbox(key="pub_sure").check().run()
    [b for b in at.button if b.label == "Publish to everyone"][0].click().run()
    assert not at.exception, at.exception
    assert load_defaults()["careers"].loc[0, "name"] == "Robotics Engineer"
    assert list_backups(), "publishing makes a backup"
    # a brand-new session starts with the published data
    fresh = new_app()
    fresh.run()
    assert "Robotics Engineer" in fresh.session_state["catalog"].careers
    # restore the backup
    at.run()
    at.checkbox(key="restore_sure").check().run()
    [b for b in at.button if b.label == "Restore"][0].click().run()
    assert load_defaults()["careers"].equals(before)


def test_data_manager_role_restriction():
    from core import settings
    _reset_accounts()
    auth.create_user("boss", "Birch2024c", "Boss")
    settings.save({"data_manager_roles": ["admin"]}, by="boss")
    at = new_app(user=STUDENT)
    at.run()
    try:
        at.switch_page("app_pages/data.py")
        reachable = True
    except ValueError:
        reachable = False
    assert not reachable, "Data manager hidden from roles the admin didn't allow"
    admin = new_app(user=auth.get_user("boss"))
    admin.switch_page("app_pages/data.py").run()
    assert not admin.exception and not admin.error
    for p in ["app_pages/overview.py", "app_pages/tutorial.py", "app_pages/literature.py"]:
        at.switch_page(p).run()
        assert not at.exception, (p, at.exception)
    settings.reset(by="test")


def test_reserved_admin_username():
    _reset_accounts()
    os.environ["COURSEPATH_ADMIN_USERNAME"] = "owner"
    try:
        assert auth.create_user("stranger", "Poplar2024g", "Stranger")[0]
        assert auth.get_user("stranger")["role"] == "student", "first account is NOT admin when a username is reserved"
        assert auth.create_user("owner", "Hazel2024h", "Owner")[0]
        assert auth.get_user("owner")["role"] == "admin"
        auth.delete_user("stranger", by="owner")
        # once an admin exists, the reserved name gives no extra power to later accounts
        users = auth._load(); del users["owner"]; users["boss2"] = {"name": "B", "role": "admin", "salt": "00", "hash": "x", "created": auth.now()}; auth._save(users)
        assert auth.create_user("owner", "Hazel2024h", "Owner")[0] and auth.get_user("owner")["role"] == "student"
        at = new_app(user=None)
        at.run()
        assert not any("becomes the administrator" in i.value for i in at.info), "don't advertise admin bootstrap when reserved"
    finally:
        os.environ["COURSEPATH_ADMIN_USERNAME"] = ""


def test_seeded_admin_account():
    _reset_accounts()
    os.environ["COURSEPATH_ADMIN_USERNAME"] = "seed_admin07"
    os.environ["COURSEPATH_ADMIN_PASSWORD_HASH"] = auth.hash_for_secret("Spruce@2024")
    try:
        assert auth.ensure_seeded_admin() is True
        assert auth.get_user("seed_admin07")["role"] == "admin"
        assert auth.authenticate("seed_admin07", "Spruce@2024") and not auth.authenticate("seed_admin07", "wrong-pass1")
        assert "Spruce@2024" not in auth.users_file().read_text(), "plain password never stored"
        assert auth.ensure_seeded_admin() is False, "idempotent"
        users = auth._load(); users["seed_admin07"]["role"] = "student"; auth._save(users)
        auth.ensure_seeded_admin()
        assert auth.get_user("seed_admin07")["role"] == "admin", "seeded account is always admin"
        users = auth._load(); del users["seed_admin07"]; auth._save(users)  # e.g. cloud restart wiped accounts
        assert auth.ensure_seeded_admin() is True and auth.authenticate("seed_admin07", "Spruce@2024")
        assert not auth.create_user("seed_admin07", "Other2024x", "Imposter")[0], "name already taken"
        os.environ["COURSEPATH_ADMIN_PASSWORD_HASH"] = "garbage"
        users = auth._load(); del users["seed_admin07"]; auth._save(users)
        assert auth.ensure_seeded_admin() is False, "malformed hash is ignored"
    finally:
        os.environ["COURSEPATH_ADMIN_USERNAME"] = ""
        os.environ["COURSEPATH_ADMIN_PASSWORD_HASH"] = ""


def test_admin_login_tab():
    _reset_accounts()
    auth.create_user("boss", "Birch2024c", "Boss")  # first account -> admin
    auth.create_user("stu", "Aspen2024d", "Stu")
    at = new_app(user=None)
    at.run()
    assert any("Admin login" in t.label for t in at.tabs)

    def admin_try(u, p):
        [t for t in at.text_input if t.label == "Admin username"][0].input(u)
        [t for t in at.text_input if t.label == "Admin password"][0].input(p)
        [b for b in at.button if b.label == "Sign in as admin"][0].click().run()

    admin_try("stu", "Aspen2024d")
    assert "user" not in at.session_state, "a non-admin can't use the admin login"
    assert any("Admin username or password is incorrect" in e.value for e in at.error)
    admin_try("boss", "Birch2024c")
    assert not at.exception, at.exception
    assert at.session_state["user"]["role"] == "admin"
    assert at.title[0].value == "Admin", "admin login lands on the Admin page"


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("PASS", t.__name__)
