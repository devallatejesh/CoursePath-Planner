# CoursePath Planner: working prototype

A Streamlit prototype of the group project from the FAI decks. It has two parts:

1. **Multi-agent roadmap planner:** the Goal, Constraint, Planning and Adaptation agents, plus guardrails and an advisor-approval step.
2. **MESA career-path simulation:** the agent-based model designed in the literature-survey slides.

The app has no built-in data. Every course, rule, career, occupation, skill, training course and study comes from tables you can replace on the **Data manager** page.

## Run

```bash
py -m pip install -r requirements.txt
py -m streamlit run streamlit_app.py
```

## Deploy online (Streamlit Community Cloud)

1. Go to https://share.streamlit.io, sign in with GitHub and choose **Create app**.
2. Repository `devallatejesh/CoursePath-Planner`, branch `main`, main file `streamlit_app.py`.
3. Under **Advanced settings**, choose Python 3.12 and add this secret, so only that username can become the administrator:

   ```toml
   COURSEPATH_ADMIN_USERNAME = "devallatejesh"
   ```
4. Deploy, then **immediately** create the account with that username on the sign-in page.

Every `git push` to `main` redeploys automatically. Free hosting has no permanent disk: accounts, settings and published data reset when the app restarts or sleeps. For permanent storage, host on a service with a persistent disk (for example Render or Railway) and point `COURSEPATH_USERS_FILE` and `COURSEPATH_DATA_DIR` at it.

## First time here?

1. Start the app and **create an account** on the sign-in page, or press **Continue as guest**. The **first account ever created becomes the administrator** (or, when `COURSEPATH_ADMIN_USERNAME` is set, the account with that username).
2. A welcome pop-up offers the **Tutorial** (top menu), a 10-minute walkthrough with **Try this** buttons that fill in example goals for you.
3. Build a roadmap, open the study links under each subject, try a re-plan, then run the career simulation.

## Admin page (administrators only)

Only accounts with the **admin** role see the page (top menu, under your name), and the stored role is re-checked on every click. Everything there is written to an audit log.

| Tab | What an admin can do |
|---|---|
| Users | Edit names and roles (student / advisor / admin), create users, generate a temporary password, delete users. You can't delete yourself or remove the last admin. |
| Site settings | App name, sign-in tagline, overview text, welcome pop-up, a banner shown on every page, whether sign-up and guests are allowed, the advisor invite code, sign-in lockout rules, and which roles may use the Data manager |
| Data | Publish your session's data as the starting data for everyone, then download or restore automatic backups (`data/backups/`) |
| Audit log | Who did what and when, filterable and downloadable |

If no admin can sign in, promote an existing account from a terminal:

```bash
py scripts/make_admin.py <username>
```

## Accounts and login

- Accounts are local to the machine running the app. They're stored in `auth/users.json` (git-ignored), with salted PBKDF2-SHA256 password hashes and no plain-text passwords. Set `COURSEPATH_USERS_FILE` to store them somewhere else.
- Roles: **student** (plan and explore), **advisor** (can also approve roadmaps) and **admin** (everything, plus the Admin page). Nobody can choose admin when signing up. The advisor invite code is set on the Admin page (or with `advisor_code` in `.streamlit/secrets.toml`).
- After 5 failed sign-ins (adjustable by an admin), a browser session is locked for 30 seconds. **Log out** (Account page) clears the session, including plans and uploaded data.
- For Google or Microsoft sign-in instead, Streamlit's built-in `st.login` (OIDC) can replace `app_pages/login.py`.

## Pages

| Page | What it does |
|---|---|
| Sign in | Create an account, sign in, or continue as guest |
| Overview | Agent flow and counts for the active datasets, plus a welcome pop-up on first visit |
| Tutorial | Step-by-step guide with example goals, explanations of every screen, and FAQ |
| Roadmap planner | Takes free-text goals and runs the 4 agents. Study resource links are shown under every subject, and there is a Study resources tab. It shows the agent trace, term-by-term roadmap, prerequisite graph, validation, career fit and CSV export, and re-plans when a course is dropped, a section is full, a course is cancelled or the goal changes. |
| Career simulation | MESA model with students, occupations, employers, training providers and an advisor. All parameters are adjustable, and it can use your uploaded student survey or clones of your roadmap graduate. |
| Scenario experiments | `mesa.batch_run` sweeping any two parameters × seeds, charting any metric |
| Literature survey | Shows the `literature` dataset |
| Account | Profile, change password, log out |
| Admin | Admins only: users, site settings, permanent data and audit log |
| Data manager | Upload (CSV / Excel / JSON / ZIP bundle), edit rows, validate, apply, download templates, or reset to the defaults |

## Datasets (`data/*.csv` are the defaults)

| File | Purpose | Key columns |
|---|---|---|
| `courses.csv` | Course catalog | `code, name, credits, category`; optional `prereqs, coreqs, terms, tags, pass_rate, capacity, counts` (lists separated by `;`) |
| `requirements.csv` | Degree rules (key/value) | `program, required_categories, required_courses, gened_category, gened_choices, elective_category, track_electives, free_electives, hard_threshold, max_hard_per_term, max_hard_if_avoiding, seasons, new_year_season` |
| `careers.csv` | Career goals | `name`; optional `track, tags, median_salary_k, keywords` |
| `occupations.csv` | Job market | `name, salary_k, automation_risk, base_demand, tags`, plus **one numeric column per skill** |
| `training.csv` | Training courses | `name, duration_months`, plus skill boost columns |
| `tag_skills.csv` | Roadmap → skills | `key` (`tag:ai` or `category:math`), plus skill columns |
| `students.csv` *(optional)* | Survey population | skill columns; optional `student_id, favourite_occupation, planned` |
| `seats.csv` *(optional)* | Registrar data | `code, term, seats_open` |
| `resources.csv` *(optional)* | Study links shown under each subject | `code, url`; optional `title, type` (reading / video / course / practice). A course can have several links. |
| `resource_links.csv` *(optional)* | Learning sites searched for every subject | `name, url_template` (contains `{query}`, which is replaced by the course name); optional `type` |
| `literature.csv` | Survey table | any columns |

Example uploads are in `data/samples/`. `biology_example.zip` is a whole different program: 3 terms a year, different categories and different skills.

Uploads are checked before they are applied. The checks cover missing columns, duplicate codes, unknown prerequisites, prerequisite cycles, bad term codes, out-of-range values, too few electives for a career track, and skill columns that don't match.

## Code

- `core/datasets.py`: specs, readers, validation, and builders (`build_catalog`, `build_market`)
- `core/catalog.py`: catalog data structures and the registrar
- `core/agents.py`: the four agents and the orchestrator
- `core/abm.py`: MESA `CareerPathModel`
- `core/state.py`: the active dataset in the Streamlit session
- `tests/test_app.py`: run with `py tests/test_app.py` (28 checks covering admin access control, login, roles, the tutorial, the planner, datasets, uploads and every page)
- `tests/fuzz.py`: run with `py tests/fuzz.py 300`. It generates random programs and job markets, chains re-plans, and checks that no hard rule is broken.

## Notes

The default data is synthetic and not calibrated. The Goal agent uses keyword matching; a tool-calling LLM can be plugged in at `GoalAgent.interpret`.
