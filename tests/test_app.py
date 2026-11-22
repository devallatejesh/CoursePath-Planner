"""Checks: curriculum data, university pages, study agents, PDF import, accounts, login and the Admin page.

Run:  py tests/test_app.py   (or pytest if installed)
"""
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
os.environ["COURSEPATH_ADMIN_EMAIL"] = ""
os.environ["COURSEPATH_ADMIN_USERNAME"] = ""
os.environ["COURSEPATH_ADMIN_PASSWORD_HASH"] = ""

from streamlit.testing.v1 import AppTest  # noqa: E402

from core import auth  # noqa: E402

APP = str(ROOT / "streamlit_app.py")
STUDENT = {"username": "tester@example.com", "name": "Test Student", "role": "student"}


def new_app(user=STUDENT):
    """An AppTest already signed in (welcome dialog already shown)."""
    at = AppTest.from_file(APP, default_timeout=180)
    # Override the real .streamlit/secrets.toml so tests never seed the real admin.
    at.secrets["COURSEPATH_ADMIN_EMAIL"] = os.environ.get("COURSEPATH_ADMIN_EMAIL", "")
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


def _page(path, at=None, user=STUDENT):
    at = at or new_app(user)
    at.run()
    at.switch_page(path).run()
    assert not at.exception, at.exception
    return at


def _reset_accounts():
    for p in (_TMP / "auth").glob("*"):
        shutil.rmtree(p) if p.is_dir() else p.unlink()


def test_curriculum_data():
    from core.curriculum import branches, load_curriculum, load_syllabus, semesters, subjects
    df, syl = load_curriculum(), load_syllabus()
    assert branches(df) == ["B.Tech CSE", "B.Tech CSE (AI)", "B.Tech ECE", "B.Tech Robotics & AI"]
    for b in branches(df):
        assert semesters(df, b) == list(range(1, 9)), b
        total = sum(s.credit_value for sem in range(1, 9) for s in subjects(df, syl, b, sem))
        assert 155 <= total <= 165, (b, total)  # each program is about 160 credits
    assert not df[df["code"] != ""].duplicated(["branch", "code"]).any(), "a subject is listed twice in a branch"
    dsa = [s for s in subjects(df, syl, "B.Tech CSE", 3) if s.code == "23CSE203"][0]
    assert dsa.title == "Data Structures and Algorithms" and dsa.credits == "5" and len(dsa.units) >= 3
    theory = [s for b in branches(df) for sem in range(1, 9) for s in subjects(df, syl, b, sem) if s.kind == "Theory" and s.code]
    with_roadmap = sum(bool(s.units) for s in theory)
    assert with_roadmap / len(theory) > 0.85, (with_roadmap, len(theory))


def test_semester_page():
    at = _page("app_pages/semester.py")
    assert at.title[0].value == "Amrita"
    assert at.selectbox(key="sem_branch_amrita").value == "B.Tech CSE"
    assert any("Computational Problem Solving" in m.value for m in at.markdown)
    for branch in ["B.Tech CSE (AI)", "B.Tech ECE", "B.Tech Robotics & AI"]:
        at.selectbox(key="sem_branch_amrita").set_value(branch).run()
        for sem in range(1, 9):
            at.segmented_control(key="sem_number_amrita").set_value(sem).run()
            assert not at.exception, (branch, sem, at.exception)
    at.selectbox(key="sem_branch_amrita").set_value("B.Tech CSE").run()
    at.segmented_control(key="sem_number_amrita").set_value(3).run()
    text = " ".join(m.value for m in at.markdown)
    assert "Data Structures and Algorithms" in text and "Step 1:" in text and "youtube.com" in text
    assert any("Learning roadmap" in e.label for e in at.expander)


def test_accounts():
    ok, msg = auth.create_user("alice@example.com", "short", "Alice")
    assert not ok and "8 characters" in msg
    ok, msg = auth.create_user("Bad Name!", "Passw0rd123", "x")
    assert not ok
    assert auth.create_user("alice@example.com", "Garden2024!", "Alice", "advisor")[0]
    assert not auth.create_user("ALICE@example.com", "Garden2024!", "Alice")[0], "emails are case-insensitive and unique"
    assert auth.authenticate("Alice@Example.com", "Garden2024!")["role"] == "advisor"
    assert auth.authenticate("alice@example.com", "wrong-pass1") is None and auth.authenticate("nobody@example.com", "x") is None
    raw = auth.users_file().read_text()
    assert "Garden2024!" not in raw and "hash" in raw, "passwords must be stored hashed"
    assert auth.change_password("alice@example.com", "Garden2024!", "Orchard2025!")[0]
    assert auth.authenticate("alice@example.com", "Orchard2025!") and not auth.authenticate("alice@example.com", "Garden2024!")


def test_login_gate_and_flow():
    at = new_app(user=None)
    at.run()
    assert not at.exception, at.exception
    assert not any("guest" in b.label.lower() for b in at.button), "there is no guest sign-in"
    assert "user" not in at.session_state, "app content must not load before sign-in"
    # create an account through the form
    at.text_input[2].input("Bob Builder")
    at.text_input[3].input("bob@example.com")
    at.text_input[4].input("Builder123")
    at.text_input[5].input("Builder123")
    [b for b in at.button if b.label == "Create account"][0].click().run()
    assert not at.exception, at.exception
    assert at.session_state["user"]["username"] == "bob@example.com"
    # log out from the Account page
    at.switch_page("app_pages/account.py").run()
    [b for b in at.button if b.label == "Log out"][0].click().run()
    assert "user" not in at.session_state
    # wrong password, then right password
    at.text_input[0].input("bob@example.com")
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
        at.text_input[0].input("ghost@example.com")
        at.text_input[1].input("wrong-pass1")
        [b for b in at.button if b.label == "Sign in"][0].click().run()
    assert [b for b in at.button if b.label == "Sign in"][0].disabled


def test_no_guest_access_and_welcome_dialog():
    # an old guest session (no stored account) is signed out and only sees the sign-in page
    at = new_app(user=None)
    at.session_state["user"] = {"username": "guest", "name": "Guest", "role": "student"}
    at.run()
    assert not at.exception, at.exception
    assert "user" not in at.session_state and any(b.label == "Sign in" for b in at.button)
    assert not any("guest" in b.label.lower() for b in at.button)
    # signing in with an account shows the welcome dialog once
    auth.create_user("wendy@example.com", "Willow2024w", "Wendy")
    at.text_input[0].input("wendy@example.com")
    at.text_input[1].input("Willow2024w")
    [b for b in at.button if b.label == "Sign in"][0].click().run()
    assert not at.exception, at.exception
    assert at.session_state["user"]["username"] == "wendy@example.com" and at.session_state["welcomed"]


def test_first_account_is_admin_and_admin_rules():
    _reset_accounts()
    assert auth.create_user("root@example.com", "Maple2024a", "Root")[0]
    assert auth.get_user("root@example.com")["role"] == "admin", "first account becomes admin"
    ok, _ = auth.create_user("eve@example.com", "Cedar2024b", "Eve", "admin")
    assert not ok, "self sign-up can't choose admin"
    assert auth.create_user("eve@example.com", "Cedar2024b", "Eve")[0] and auth.get_user("eve@example.com")["role"] == "student"
    assert not auth.update_user("root@example.com", role="student", by="root@example.com")[0], "can't demote the last admin"
    assert not auth.delete_user("root@example.com", by="root@example.com")[0], "can't delete yourself"
    assert auth.update_user("eve@example.com", role="admin", name="Eve A", by="root@example.com")[0]
    assert auth.update_user("root@example.com", role="advisor", by="eve@example.com")[0], "allowed once another admin exists"
    temp = auth.temporary_password()
    assert auth.reset_password("root@example.com", temp, by="eve@example.com")[0] and auth.authenticate("root@example.com", temp)
    assert auth.delete_user("root@example.com", by="eve@example.com")[0] and auth.get_user("root@example.com") is None
    actions = {r["action"] for r in auth.read_audit()}
    assert {"create user", "edit user", "reset password", "delete user"} <= actions


def test_admin_page_access_control():
    _reset_accounts()
    auth.create_user("boss@example.com", "Birch2024c", "Boss")  # admin
    auth.create_user("stu@example.com", "Aspen2024d", "Stu")
    def admin_reachable(at):
        try:
            at.switch_page("app_pages/admin.py")
            return True
        except ValueError:  # the page isn't registered in this user's navigation at all
            return False

    at = new_app(user=auth.get_user("stu@example.com"))
    at.run()
    assert not admin_reachable(at), "students must not be able to open the Admin page"
    # a forged role in the session is not enough: the stored role is checked on every run
    at = new_app(user={"username": "stu@example.com", "name": "Stu", "role": "admin"})
    at.run()
    assert at.session_state["user"]["role"] == "student", "role is refreshed from the account store"
    assert not admin_reachable(at)
    # an admin who is demoted loses access on the next interaction
    auth.create_user("temp-admin@example.com", "Spruce2024f", "Temp", "admin", by="boss@example.com")
    at = new_app(user=auth.get_user("temp-admin@example.com"))
    at.run()
    assert admin_reachable(at)
    auth.update_user("temp-admin@example.com", role="student", by="boss@example.com")
    at.run()
    assert not admin_reachable(at)
    # the real admin gets in
    at = new_app(user=auth.get_user("boss@example.com"))
    at.switch_page("app_pages/admin.py").run()
    assert not at.exception and not at.error, (at.exception, [e.value for e in at.error])
    assert at.title[0].value == "Admin"


def test_admin_edits_users_and_settings():
    _reset_accounts()
    auth.create_user("boss@example.com", "Birch2024c", "Boss")
    auth.create_user("stu@example.com", "Aspen2024d", "Stu")
    at = new_app(user=auth.get_user("boss@example.com"))
    at.switch_page("app_pages/admin.py").run()
    # create a user from the admin form
    at.text_input[0].input("New Advisor")
    at.text_input[1].input("newadv@example.com")
    at.selectbox[0].set_value("advisor")
    at.text_input[2].input("Larch2024e")
    [b for b in at.button if b.label == "Create user"][0].click().run()
    assert not at.exception, at.exception
    assert auth.get_user("newadv@example.com")["role"] == "advisor"
    # reset a password
    at.selectbox(key="reset_user").set_value("stu@example.com").run()
    [b for b in at.button if b.label == "Generate a temporary password"][0].click().run()
    temp = at.session_state["last_temp"][1]
    assert auth.authenticate("stu@example.com", temp)
    # delete a user
    at.selectbox(key="del_user").set_value("newadv@example.com").run()
    at.checkbox(key="del_sure").check().run()
    [b for b in at.button if b.label == "Delete user"][0].click().run()
    assert auth.get_user("newadv@example.com") is None
    # site settings: rename the app, add a banner, turn off sign-up
    at.text_input[at.text_input.values.index("CoursePath planner")].input("Uni Planner")
    banner = [t for t in at.text_input if t.label == "Banner text"][0]
    banner.input("Registration closes Friday")
    assert not any("guest" in t.label.lower() for t in at.toggle)
    [t for t in at.toggle if t.label == "Allow people to create accounts"][0].set_value(False)
    [b for b in at.button if b.label == "Save settings"][0].click().run()
    assert not at.exception, at.exception
    from core import settings
    cfg = settings.load()
    assert cfg["app_name"] == "Uni Planner" and cfg["announcement"] and not cfg["allow_signup"] and "allow_guest" not in cfg
    at.switch_page("app_pages/overview.py").run()
    assert at.title[0].value == "Uni Planner"
    assert any("Registration closes Friday" in i.value for i in at.info)
    login = new_app(user=None)
    login.run()
    assert not any("Create account" in t.label for t in login.tabs)
    settings.reset(by="test")


def test_reserved_admin_username():
    _reset_accounts()
    os.environ["COURSEPATH_ADMIN_EMAIL"] = "owner@example.com"
    try:
        assert auth.create_user("stranger@example.com", "Poplar2024g", "Stranger")[0]
        assert auth.get_user("stranger@example.com")["role"] == "student", "first account is NOT admin when a username is reserved"
        assert auth.create_user("owner@example.com", "Hazel2024h", "Owner")[0]
        assert auth.get_user("owner@example.com")["role"] == "admin"
        auth.delete_user("stranger@example.com", by="owner@example.com")
        # once an admin exists, the reserved name gives no extra power to later accounts
        users = auth._load(); del users["owner@example.com"]; users["boss2@example.com"] = {"name": "B", "role": "admin", "salt": "00", "hash": "x", "created": auth.now()}; auth._save(users)
        assert auth.create_user("owner@example.com", "Hazel2024h", "Owner")[0] and auth.get_user("owner@example.com")["role"] == "student"
        at = new_app(user=None)
        at.run()
        assert not any("becomes the administrator" in i.value for i in at.info), "don't advertise admin bootstrap when reserved"
    finally:
        os.environ["COURSEPATH_ADMIN_EMAIL"] = ""


def test_seeded_admin_account():
    _reset_accounts()
    os.environ["COURSEPATH_ADMIN_EMAIL"] = "seed_admin07@example.com"
    os.environ["COURSEPATH_ADMIN_PASSWORD_HASH"] = auth.hash_for_secret("Spruce@2024")
    try:
        assert auth.ensure_seeded_admin() is True
        assert auth.get_user("seed_admin07@example.com")["role"] == "admin"
        assert auth.authenticate("seed_admin07@example.com", "Spruce@2024") and not auth.authenticate("seed_admin07@example.com", "wrong-pass1")
        assert "Spruce@2024" not in auth.users_file().read_text(), "plain password never stored"
        assert auth.ensure_seeded_admin() is False, "idempotent"
        users = auth._load(); users["seed_admin07@example.com"]["role"] = "student"; auth._save(users)
        auth.ensure_seeded_admin()
        assert auth.get_user("seed_admin07@example.com")["role"] == "admin", "seeded account is always admin"
        users = auth._load(); del users["seed_admin07@example.com"]; auth._save(users)  # e.g. cloud restart wiped accounts
        assert auth.ensure_seeded_admin() is True and auth.authenticate("seed_admin07@example.com", "Spruce@2024")
        assert not auth.create_user("seed_admin07@example.com", "Other2024x", "Imposter")[0], "name already taken"
        os.environ["COURSEPATH_ADMIN_PASSWORD_HASH"] = "garbage"
        users = auth._load(); del users["seed_admin07@example.com"]; auth._save(users)
        assert auth.ensure_seeded_admin() is False, "malformed hash is ignored"
    finally:
        os.environ["COURSEPATH_ADMIN_EMAIL"] = ""
        os.environ["COURSEPATH_ADMIN_PASSWORD_HASH"] = ""


def test_admin_login_tab():
    _reset_accounts()
    auth.create_user("boss@example.com", "Birch2024c", "Boss")  # first account -> admin
    auth.create_user("stu@example.com", "Aspen2024d", "Stu")
    at = new_app(user=None)
    at.run()
    assert any("Admin login" in t.label for t in at.tabs)

    def admin_try(u, p):
        [t for t in at.text_input if t.label == "Admin email"][0].input(u)
        [t for t in at.text_input if t.label == "Admin password"][0].input(p)
        [b for b in at.button if b.label == "Sign in as admin"][0].click().run()

    admin_try("stu@example.com", "Aspen2024d")
    assert "user" not in at.session_state, "a non-admin can't use the admin login"
    assert any("Admin email or password is incorrect" in e.value for e in at.error)
    admin_try("boss@example.com", "Birch2024c")
    assert not at.exception, at.exception
    assert at.session_state["user"]["role"] == "admin"
    assert at.title[0].value == "Admin", "admin login lands on the Admin page"


def test_email_accounts():
    _reset_accounts()
    for bad in ("bob", "bob@", "bob@example", "two words@example.com", "guest"):
        assert not auth.create_user(bad, "Garden2024!", "Bob")[0], bad
    ok, msg = auth.create_user("Bob.Smith+cse@Uni.Example.edu", "Garden2024!", "Bob")
    assert ok, msg
    assert auth.authenticate("bob.smith+cse@uni.example.edu", "Garden2024!")
    assert "email" in auth.create_user("bob.smith+cse@uni.example.edu", "Garden2024!", "Bob")[1]
    assert "email name" in auth.create_user("carol@example.com", "carol12345", "Carol")[1]
    # an older username-style admin from the secrets keeps working
    os.environ["COURSEPATH_ADMIN_USERNAME"] = "legacyadmin"
    try:
        assert auth.create_user("legacyadmin", "Hazel2024h", "Legacy")[0]
    finally:
        os.environ["COURSEPATH_ADMIN_USERNAME"] = ""
    at = new_app(user=None)
    at.run()
    assert [t.label for t in at.text_input][:2] == ["Email", "Password"]


def test_study_agents():
    from core.curriculum import load_curriculum, load_syllabus, subjects
    from core.study_agents import AGENT_NAMES, plan_rows, run_agents
    df, syl = load_curriculum(), load_syllabus()
    subs = subjects(df, syl, "B.Tech CSE", 5)
    bb = run_agents(subs, "I want AI/ML placements", weeks=16, hours_per_week=20, revision_weeks=2)
    assert [a for a, _, _ in bb.trace] == AGENT_NAMES
    assert len(bb.weeks) == 14 and sum(len(w) for w in bb.weeks) == len(bb.topics) > 50
    assert max(bb.week_hours) <= 20 * 1.25, bb.week_hours
    ranked = sorted(bb.subject_scores.items(), key=lambda kv: -kv[1][0])
    assert ranked[0][0] == "Machine Learning", ranked[:3]
    assert all(t.links.get("YouTube", "").startswith("https://www.youtube.com/") for t in bb.topics)
    for subject in {t.subject for t in bb.topics}:  # each subject's topics stay in syllabus order
        steps = [t.step for w in bb.weeks for t in w if t.subject == subject]
        assert steps == sorted(steps), subject
    rows = plan_rows(bb)
    assert rows[-1]["Week"] == 16 and "Revision" in rows[-1]["Topic"]
    # no goal: equal priority, and a tiny budget is flagged by the Review agent
    bb = run_agents(subs, "", weeks=16, hours_per_week=4, revision_weeks=0)
    assert len({s for s, _ in bb.subject_scores.values()}) == 1
    assert any("revision" in m.lower() for _, m in bb.issues)
    # every branch and semester can be planned
    for b in df["branch"].unique():
        for sem in range(1, 9):
            bb = run_agents(subjects(df, syl, b, sem), "GATE", 16, 25, 2)
            assert sum(len(w) for w in bb.weeks) == len(bb.topics), (b, sem)


def test_agents_on_page():
    at = _page("app_pages/semester.py")
    at.segmented_control(key="sem_number_amrita").set_value(5).run()
    at.text_input(key="agent_goal").input("AI placements")
    [b for b in at.button if b.label == "Run the agents"][0].click().run()
    assert not at.exception, at.exception
    text = " ".join(m.value for m in at.markdown)
    for name in ("Profile agent", "Syllabus agent", "Priority agent", "Scheduler agent", "Resource agent", "Review agent"):
        assert name in text, name
    assert any(e.label.startswith("Week 1:") for e in at.expander)
    assert len(at.dataframe) >= 1


def _sample_pdf() -> bytes:
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page()
    lines = [
        "B.Tech Mechanical Engineering", "", "Semester I",
        "Cat  Code  Title  L-T-P  Credits",
        "SCI  ME101  Engineering Mathematics  3-1-0  4",
        "ENG  ME102  Engineering Mechanics  3-0-0  3",
        "ENG  ME181  Workshop Lab  0-0-3  1",
        "", "Semester II",
        "ENG  ME201  Thermodynamics  3-1-0  4",
        "ENG  ME202  Strength of Materials  3-0-0  3",
        "ENG  Professional Elective I  3",
    ]
    y = 60
    for line in lines:
        page.insert_text((50, y), line, fontsize=10)
        y += 18
    page = doc.new_page()
    text = ("ME201 Thermodynamics\nSyllabus\nUnit 1\nBasic concepts - system, surroundings, properties and state.\n"
            "Unit 2\nFirst law of thermodynamics - energy, work and heat transfer.\nUnit 3\nSecond law - entropy, "
            "Carnot cycle and efficiency.\nTextbooks\n1. P K Nag, Engineering Thermodynamics, McGraw Hill, 2017.\nReferences\n")
    page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def test_pdf_import_and_new_university():
    from core.curriculum import delete_university, get_university, list_universities, load_curriculum, load_syllabus
    from core.pdf_import import import_pdf
    df, syl, notes, program = import_pdf(_sample_pdf(), "B.Tech Mechanical")
    assert program.startswith("B.Tech Mechanical")
    got = {(r.semester, r.code, r.title, r.credits) for r in df.itertuples()}
    assert (1, "ME101", "Engineering Mathematics", "4") in got and (2, "ME201", "Thermodynamics", "4") in got
    assert (2, "", "Professional Elective I", "3") in got
    assert df.loc[df.code == "ME102", "ltp"].item() == "3-0-0"
    assert len(syl["ME201"]["units"]) == 3 and "First law" in syl["ME201"]["units"][1]
    assert "Nag" in syl["ME201"]["textbooks"][0]

    from core.curriculum import save_university
    u = save_university("Test Institute of Technology", "TIT", df, syl, source="sample.pdf",
                        added_by="bob@example.com", added_by_name="Bob")
    try:
        assert [x.slug for x in list_universities()] == ["amrita", "alliance", "dsu", "klu", u.slug]
        assert len(load_curriculum(u)) == len(df) and "ME201" in load_syllabus(u)
        at = new_app()
        at.run()
        menu_titles = [p.title for p in at.session_state["uni_pages"].values()]
        assert menu_titles == ["Amrita", "Alliance", "DSU", "KLU", "TIT"]
        assert get_university(u.slug).added_by_name == "Bob"
    finally:
        assert delete_university(u.slug)
    assert not delete_university("amrita"), "built-in universities can't be deleted"
    assert [x.slug for x in list_universities()] == ["amrita", "alliance", "dsu", "klu"]


def test_add_university_page():
    at = _page("app_pages/add_university.py")
    assert not at.exception, at.exception
    assert any(b.label == "Read the PDFs" for b in at.button)
    # review step, as if the PDFs were read
    from core.pdf_import import import_pdf
    df, syl, notes, program = import_pdf(_sample_pdf())
    at.session_state["uni_draft"] = dict(name="Test Institute", short="TI",
                                         parts=[dict(file="mech.pdf", branch=program, df=df, syl=syl, notes=notes)])
    at.run()
    assert not at.exception, at.exception
    [b for b in at.button if b.label == "Save the university"][0].click().run()
    assert not at.exception, at.exception
    from core.curriculum import delete_university, list_universities
    added = [u for u in list_universities() if not u.built_in]
    assert [u.short_name for u in added] == ["TI"] and added[0].added_by == STUDENT["username"]
    assert "TI" in [p.title for p in at.session_state["uni_pages"].values()]
    delete_university(added[0].slug)


def test_alliance_university():
    from core.curriculum import branches, get_university, load_curriculum, load_syllabus, semesters, subjects
    from core.study_agents import run_agents
    u = get_university("alliance")
    assert u and u.built_in and u.short_name == "Alliance"
    df, syl = load_curriculum(u), load_syllabus(u)
    assert branches(df) == ["B.Tech CSE", "B.Tech AI & ML", "B.Tech ECE"]
    for b in branches(df):
        assert semesters(df, b) == list(range(1, 9)), b
    ece5 = {s.title: s for s in subjects(df, syl, "B.Tech ECE", 5)}
    assert "Digital Signal Processing" in ece5 and ece5["Minor Elective - II"].kind == "Elective"
    assert ece5["Activity Points 5"].kind == "Activity"
    dsp = ece5["Digital Signal Processing"]
    assert not dsp.has_official_syllabus and len(dsp.outline) == 4 and "Digital Signal Processing" in dsp.outline[0]
    bb = run_agents(subjects(df, syl, "B.Tech CSE", 5), "cyber security", 16, 20, 2)
    assert sum(len(w) for w in bb.weeks) == len(bb.topics) > 0
    assert max(bb.subject_scores.items(), key=lambda kv: kv[1][0])[0] == "Cryptography and Network Security"
    assert any("general study outline" in m for _, m in bb.issues)


def test_dsu_university():
    from core.curriculum import branches, get_university, load_curriculum, load_syllabus, semesters, subjects
    u = get_university("dsu")
    assert u and u.built_in and u.short_name == "DSU"
    df, syl = load_curriculum(u), load_syllabus(u)
    assert branches(df) == ["B.Tech CSE", "B.Tech CSE (AI & ML)", "B.Tech CSE (Cyber Security)", "B.Tech ECE"]
    expected = {"B.Tech CSE": 161, "B.Tech CSE (AI & ML)": 160, "B.Tech CSE (Cyber Security)": 130, "B.Tech ECE": 162}
    for b, total in expected.items():
        got = sum(s.credit_value for sem in semesters(df, b) for s in subjects(df, syl, b, sem))
        assert got == total, (b, got)  # matches the credit totals printed in DSU's schemes
    assert semesters(df, "B.Tech CSE (Cyber Security)") == [1, 2, 3, 4, 5, 6]
    assert not df[df["code"] != ""].duplicated(["branch", "code"]).any()
    dl = [s for s in subjects(df, syl, "B.Tech CSE (AI & ML)", 6) if s.code == "24AM3601"][0]
    assert dl.title == "Deep Learning" and len(dl.units) >= 4 and not any("Hours" in x for x in dl.units)
    coded = [s for b in branches(df) for sem in semesters(df, b) for s in subjects(df, syl, b, sem)
             if s.kind == "Theory" and s.code]
    assert sum(s.has_official_syllabus for s in coded) / len(coded) > 0.9


def test_recommended_resources():
    from core.resources import STRIVER_A2Z, is_dsa, recommended
    urls = lambda t: [u for _, _, u in recommended(t)]
    assert STRIVER_A2Z in urls("Data Structures and Algorithms") and is_dsa("Design and Analysis of Algorithms")
    assert not is_dsa("Engineering Chemistry") and STRIVER_A2Z not in urls("Engineering Chemistry")
    assert "https://www.w3schools.com/python/" in urls("Computational Thinking with Python")
    assert "https://www.w3schools.com/sql/" in urls("Database Management Systems")
    assert "https://www.w3schools.com/java/" in urls("Programming in JAVA")
    assert "https://www.w3schools.com/c/" in urls("C Programming for Problem Solving")
    for t in ("Engineering Chemistry", "Machine Learning", "Data Structures"):
        assert urls(t)[-1].startswith("https://www.youtube.com/results?search_query="), t
    at = _page("app_pages/semester.py")
    at.segmented_control(key="sem_number_amrita").set_value(3).run()
    text = " ".join(m.value for m in at.markdown)
    assert "takeuforward.org" in text and "w3schools.com/sql" in text
    at.text_input(key="agent_goal").input("placements")
    [b for b in at.button if b.label == "Run the agents"][0].click().run()
    assert not at.exception, at.exception
    assert "Striver A2Z DSA Sheet" in " ".join(m.value for m in at.markdown)


def test_klu_university():
    from core.curriculum import branches, get_university, load_curriculum, load_syllabus, semesters, subjects
    from core.study_agents import run_agents
    u = get_university("klu")
    assert u and u.built_in and u.short_name == "KLU"
    df, syl = load_curriculum(u), load_syllabus(u)
    assert branches(df) == ["B.Tech CSE", "B.Tech ECE"]
    for b in branches(df):
        assert semesters(df, b) == list(range(1, 16)), b  # 12 trimesters + 3 summer terms
        assert sum(s.credit_value for sem in range(1, 16) for s in subjects(df, syl, b, sem)) == 185
    assert [u.term_label(n) for n in (1, 3, 4, 5, 15)] == ["T1", "T3", "Summer 1", "T4", "T12"]
    dsa1 = [s for s in subjects(df, syl, "B.Tech CSE", 2) if s.code == "25SC1204E"][0]
    assert dsa1.title == "Data Structures and Algorithms - 1" and len(dsa1.units) == 6
    assert dsa1.resources and dsa1.project and dsa1.textbooks
    assert "�" not in df.to_csv() and all(s.kind == "Activity" for s in subjects(df, syl, "B.Tech CSE", 6)
                                                    if s.title.startswith("Value Added"))
    bb = run_agents(subjects(df, syl, "B.Tech ECE", 9), "VLSI", 12, 25, 1)
    assert sum(len(w) for w in bb.weeks) == len(bb.topics) > 0
    assert any(k.endswith(" course") for t in bb.topics for k in t.links)
    at = _page("app_pages/semester.py")  # Amrita still uses "Sem" labels
    assert at.segmented_control(key="sem_number_amrita").options[0] == "Sem 1"


def test_geeksforgeeks_links():
    from core.resources import recommended
    sites = lambda t: {x[0] for x in recommended(t)}
    for t in ("Operating Systems", "Compiler Design", "Computer Networks", "Machine Learning", "Signal Processing",
              "Digital Communication", "CMOS VLSI Design", "Engineering Physics"):
        assert "GeeksforGeeks" in sites(t) and "YouTube" in sites(t), t
    for t in ("Communication Skills for Engineers", "Mastery Over Mind", "Value Added Course 1 - Sports"):
        assert "GeeksforGeeks" not in sites(t), t
    assert [x[0] for x in recommended("Data Structures")][:3] == ["Striver", "Striver", "W3Schools"]


def test_subject_search():
    from core.subject_search import best_roadmap, build_index, search
    idx = build_index()
    assert len(idx) > 600
    for q, expect in [("dsa", "Data Structures"), ("os", "Operating Systems"), ("operating sytems", "Operating Systems"),
                      ("DBMS", "Database Management"), ("machine lerning", "Machine Learning"), ("coa", "Computer Organization")]:
        hits = search(q, idx)
        assert hits and expect in hits[0].subject.title, (q, [h.subject.title for h in hits[:3]])
        b = best_roadmap(hits)
        assert b and b.subject.kind == "Theory" and len(b.subject.units) >= 3, q
    assert best_roadmap(search("quantum computing", idx)) is None, "partial word matches are not used as the roadmap"
    assert search("react js", idx) == []
    # the page: shows a roadmap, resources and where the subject is taught
    at = _page("app_pages/subject_search.py")
    assert at.title[0].value == "Subject search"
    at.text_input(key="subject_query").input("Operating Systems").run()
    assert not at.exception, at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "Step 1:" in text and "geeksforgeeks.org" in text and "youtube.com" in text
    assert any("Where it's taught" in t.label for t in at.tabs)
    assert any("Amrita" in e.label for e in at.expander) and any("DSU" in e.label for e in at.expander)
    at.text_input(key="subject_query").input("Quantum Computing").run()
    assert not at.exception, at.exception
    assert any("general study outline" in i.value for i in at.info)
    assert "Step 4:" in " ".join(m.value for m in at.markdown)


def test_removed_features_are_gone():
    """Data manager, experiments, literature, simulation and the agent Roadmap planner were removed."""
    for path in ["app_pages/data.py", "app_pages/experiments.py", "app_pages/literature.py", "app_pages/simulation.py",
                 "app_pages/planner.py", "core/abm.py", "core/agents.py", "core/catalog.py", "core/datasets.py",
                 "data/courses.csv", "data/occupations.csv", "data/samples"]:
        assert not (ROOT / path).exists(), path
    _reset_accounts()
    auth.create_user("boss@example.com", "Birch2024c", "Boss")
    for user in (STUDENT, auth.get_user("boss@example.com")):
        at = new_app(user=user)
        at.run()
        assert not at.exception, at.exception
        for p in ("app_pages/data.py", "app_pages/experiments.py", "app_pages/literature.py",
                  "app_pages/simulation.py", "app_pages/planner.py"):
            try:
                at.switch_page(p)
                reachable = True
            except ValueError:
                reachable = False
            assert not reachable, (user["username"], p)
        for p in ("app_pages/overview.py", "app_pages/tutorial.py", "app_pages/account.py"):
            at.switch_page(p).run()
            assert not at.exception, (p, at.exception)
            text = " ".join(str(getattr(e, "value", "")) for e in list(at.markdown) + list(at.caption))
            for word in ("Data manager", "Scenario experiments", "Literature survey", "Career simulation",
                         "Roadmap planner", "MESA", "synthetic"):
                assert word not in text, (p, word)
    admin = new_app(user=auth.get_user("boss@example.com"))
    admin.switch_page("app_pages/admin.py").run()
    assert not admin.exception
    assert [t.label for t in admin.tabs] == [":material/group: Users", ":material/tune: Site settings", ":material/history: Audit log"]


def test_pages_render():
    for p in ["app_pages/overview.py", "app_pages/semester.py", "app_pages/subject_search.py", "app_pages/tutorial.py", "app_pages/account.py"]:
        _page(p)


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("PASS", t.__name__)
