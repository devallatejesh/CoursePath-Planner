# CoursePath Planner

A Streamlit app that shows every subject of a B.Tech semester with a step-by-step learning roadmap, matched study
resources and six study agents that build a weekly study plan. It ships with four universities, any college can be
added from its curriculum PDF, and any subject can be searched without picking a university.

## Run

```bash
py -m pip install -r requirements.txt
py -m streamlit run streamlit_app.py
```

Open http://localhost:8501. Requires Python 3.11 or newer.

## Pages

| Page | What it does |
|---|---|
| Sign in | Sign in with your email, create an account, or use the Admin login tab |
| Overview | The universities in the app and what every subject page offers |
| Subject search | Type any subject (short forms like `dsa`, `os`, `dbms` and small typos work). Shows a roadmap from the closest official syllabus (or a labelled general outline), matched resources, and every university, branch and term that teaches it |
| Tutorial | A 4-minute walkthrough |
| Universities → *college* | Pick a branch and semester/term. **Subjects and roadmaps** tab: subject details, learning roadmap from the syllabus units, recommended links, textbooks, the university's own course picks and projects. **Study agents** tab: weekly study plan |
| Universities → Add a university | Upload curriculum/syllabus PDFs (one per branch), review the table the app reads, and save. The college then appears in the Universities menu |
| Account | Change password, log out |
| Admin | Admins only: users, site settings, audit log |

## Universities included

| University | Branches | Source |
|---|---|---|
| Amrita Vishwa Vidyapeetham | B.Tech CSE, CSE (AI), ECE, Robotics & AI | Curriculum and syllabus PDFs (2022-2024) |
| Alliance University | B.Tech CSE, AI & ML, ECE | alliance.edu.in course structures (names and categories only, so subjects use a labelled general outline) |
| Dayananda Sagar University (DSU) | B.Tech CSE, CSE (AI & ML), CSE (Cyber Security), ECE | DSU schemes and syllabi (2024-28 batch; CSE semesters 3-8 from the 2020-21 scheme; Cyber semesters 1-6 published) |
| KL University (KLU) | B.Tech CSE, ECE (PBL trimester mode: T1-T12 + 3 summer terms) | y25btech.klef.in, 2025-29 |

Data lives in `data/universities/<slug>/` (`meta.json`, `curriculum.csv`, `syllabus.json`). Universities added by users
are stored in `auth/universities/` (git-ignored).

## Study resources

`core/resources.py` matches each subject title to checked links: W3Schools and GeeksforGeeks tutorials, Striver's A2Z
DSA sheet and SDE sheet for DSA subjects, a GeeksforGeeks search for other technical subjects, and a YouTube full-course
search. Every roadmap step also links to YouTube and NPTEL videos for that step.

## Study agents

`core/study_agents.py`: Profile → Syllabus → Priority → Scheduler → Resource → Review. They read a goal (AI/ML,
placements, GATE, VLSI, robotics, software, research, cyber security), the semester length and study hours, split the
syllabus into topics, rank subjects for the goal, spread topics evenly over the weeks, attach links and check the plan.

## Accounts, admin and secrets

- Sign-in uses an **email address**. Passwords are stored as salted PBKDF2-SHA256 hashes in `auth/users.json` (git-ignored).
- Roles: student, advisor, admin. Nobody can pick admin at sign-up.
- **Built-in administrator**: set these secrets (locally in `.streamlit/secrets.toml`, which is git-ignored, and in the
  app's **Secrets** on Streamlit Community Cloud). The account is recreated automatically whenever it is missing.

  ```toml
  COURSEPATH_ADMIN_EMAIL = "you@example.com"
  COURSEPATH_ADMIN_PASSWORD_HASH = "pbkdf2_sha256$..."
  COURSEPATH_ADMIN_DISPLAY_NAME = "Your Name"
  ```

  Make the hash with `py scripts/hash_password.py you@example.com "Your Name"` (it asks for the password and never
  stores it). Promote an existing account from a terminal with `py scripts/make_admin.py <email>`.

## Deploy (Streamlit Community Cloud)

Repository `devallatejesh/CoursePath-Planner`, branch `main`, main file `streamlit_app.py`, Python 3.12, and the three
secrets above. Every push to `main` redeploys. Free hosting has no permanent disk: accounts and universities added from
PDFs reset when the app restarts or sleeps (the built-in admin comes back automatically).

## Tests

```bash
py tests/test_app.py
```

Covers the curriculum data of every university, the semester pages, study agents, subject search, resources, PDF import,
adding a university, accounts, email sign-in, the admin page and access control.

## Code

- `core/curriculum.py`: universities, subjects, roadmap helpers
- `core/study_agents.py`: the six study agents
- `core/subject_search.py`: the subject search index and ranking
- `core/resources.py`: W3Schools, GeeksforGeeks, Striver and YouTube links per subject
- `core/pdf_import.py`: reads curriculum/syllabus PDFs
- `core/auth.py`, `core/settings.py`: accounts, audit log, site settings
- `app_pages/`: one file per page
