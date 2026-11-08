# SkillSwap – AI-Powered Student Skill Exchange Platform

A college-project MVP built with HTML, CSS, JavaScript, Python Flask, Supabase PostgreSQL, Google Gemini and LinkedIn verification.

## 1. Project overview

Students register, describe skills they can teach and skills they want to learn, verify their identity with LinkedIn, discover compatible students, send learning requests, chat after a request is accepted, plan learning sessions with their partner, review each other, share a public profile link and generate a four-week learning roadmap with Gemini AI.

### Features

| Area | What it does |
|---|---|
| Accounts | Register / login with JWT, hashed passwords, automatic logout when the session expires |
| Profile | College, branch, year, bio, LinkedIn link, profile-completeness score, add **and remove** skills |
| LinkedIn verification | "Verify with LinkedIn" (OpenID Connect) cross-checks the LinkedIn name and email against the profile. Matching profiles get a **✓ LinkedIn verified** badge; mismatches are shown side by side with a one-click fix. One LinkedIn account can verify only one SkillSwap account, and changing your name after verifying re-runs the check |
| Public profile link | Opt-in toggle. `user.html?id=N` is viewable by anyone when public (email is never shown) |
| Matching | Rule-based: two-way swaps rank first, extra overlapping skills add points; search and "verified only" filters |
| Requests | Accept / decline incoming, cancel sent, no duplicate or reverse-pending requests, 7-day cooldown after a decline |
| Messages | Partner list (no typing IDs), auto-refresh every 5 seconds, Enter to send |
| Sessions | Plan sessions with a partner, both partners see them, mark completed / cancelled |
| Reviews | 1–5 star reviews for connected partners, average rating shown on cards and profiles |
| AI roadmap | Gemini generates a 4-week plan, rendered with headings and lists, copy / print |
| Dashboard | Live counts, profile checklist, LinkedIn status, upcoming sessions |

## 2. Technology stack

- Frontend: HTML5, CSS3, vanilla JavaScript
- Backend: Python Flask and REST API routes
- Database: Supabase PostgreSQL
- ORM/driver: Flask-SQLAlchemy and Psycopg 3
- Authentication: JWT and Werkzeug password hashing
- AI: Google Gemini API through the `google-genai` SDK
- Identity: Sign In with LinkedIn using OpenID Connect
- Hosting: Render (one web service serves the pages and the API)
- Version control: Git and GitHub

## 3. Requirements

Install:
1. Python 3.10 or later
2. Git
3. Visual Studio Code
4. VS Code extension: Live Server
5. A Supabase account
6. A Google AI Studio API key (only needed for AI roadmap generation)
7. A LinkedIn developer app (only needed for LinkedIn verification – see section 8A)

## 4. Create the Supabase database

1. Visit https://supabase.com/dashboard and sign in.
2. Select **New project**.
3. Set project name to `SkillSwap`, create a strong database password, and choose a nearby region.
4. Wait for the project to finish provisioning.
5. Open the project and select **Connect**.
6. Choose the PostgreSQL **Session pooler** connection option for local development if your network is IPv4-only. If using a direct connection, your network/runtime must support its connection requirements.
7. Copy the connection string. It will resemble:

   `postgresql://postgres.PROJECT_REF:PASSWORD@POOLER_HOST:5432/postgres`

8. Keep the database password private. If it contains URL-reserved characters (for example `@`, `#`, `/`), URL-encode those characters before placing it in the URL.
9. Do not expose database credentials or service-role keys in frontend code.

The database itself is created by Supabase. The Flask app creates the application tables from the SQLAlchemy models at startup (`db.create_all()`), and automatically adds the new columns if your database was created by an older version. `database/schema.sql` contains the same schema as plain SQL if you prefer to paste it into the Supabase SQL Editor.

## 5. Open the project in VS Code

1. Extract the ZIP.
2. Open VS Code.
3. Select **File -> Open Folder**.
4. Select the extracted `SkillSwap` folder (the folder containing `frontend`, `backend`, and `database`).
5. Open **Terminal -> New Terminal**.

## 6. Configure the backend

In the VS Code terminal, from the project root:

### Windows PowerShell

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

### Create the environment file

1. In VS Code Explorer, right-click `backend`.
2. Select **New File** and name it `.env`.
3. Copy the contents of `.env.example` into `.env`.
4. Replace the placeholders:

```env
SECRET_KEY=your-long-random-secret
JWT_SECRET_KEY=another-long-random-secret
DATABASE_URL=postgresql://postgres.PROJECT_REF:YOUR_PASSWORD@POOLER_HOST:5432/postgres?sslmode=require
GEMINI_API_KEY=your-api-key
GEMINI_MODEL=gemini-3.5-flash-lite
LINKEDIN_CLIENT_ID=from-your-linkedin-app
LINKEDIN_CLIENT_SECRET=from-your-linkedin-app
```

Use your real Supabase connection string. The Gemini model shown is an example; choose a model currently available to your API key in Google AI Studio. Keep `.env` private and never upload it to GitHub.

## 7. Run the backend

Make sure the terminal is in `backend` and the virtual environment is active:

```powershell
python app.py
```

The API should start at:

`http://127.0.0.1:5000`

Test the health route in a browser:

`http://127.0.0.1:5000/api/health`

Then open Supabase -> **Table Editor**. The app should have created tables named `users`, `skills`, `user_skills`, `match_requests`, `messages`, `sessions`, and `reviews`.

If the app reports a database connection error:
- Recheck the entire `DATABASE_URL`.
- Confirm the database password is correct and URL-encoded where necessary.
- Check whether you copied the Session Pooler URL and its port/host exactly.
- Confirm the network allows the database connection.
- Keep `?sslmode=require` in the connection URL.

## 8. Run the frontend

Flask now serves the website too, so the easiest way is simply to open:

`http://127.0.0.1:5000`

Live Server still works if you prefer it (open `frontend/index.html` → **Open with Live Server**); pages served on port 5500 automatically call the API at `http://127.0.0.1:5000/api`. On any other address (for example Render) the pages call `/api` on the same site.

Register two test students in two different browsers (or one normal + one private window), give them complementary skills and test requests, chat, sessions and reviews.

## 8A. Set up LinkedIn verification

1. Go to https://www.linkedin.com/developers/apps and select **Create app**. LinkedIn requires a LinkedIn Page for the app; you can create a simple page for SkillSwap.
2. In the app's **Products** tab, request **Sign In with LinkedIn using OpenID Connect** (approved instantly).
3. In the **Auth** tab, copy the **Client ID** and **Client Secret** into `.env` as `LINKEDIN_CLIENT_ID` and `LINKEDIN_CLIENT_SECRET`.
4. Still in **Auth**, under **Authorized redirect URLs**, add:
   - `http://127.0.0.1:5000/api/linkedin/callback` (local)
   - `https://YOUR-APP.onrender.com/api/linkedin/callback` (live site)
5. Restart Flask. On **My profile → Verify with LinkedIn**, students sign in to LinkedIn and come back verified (or see a name mismatch to fix).

What is checked: LinkedIn returns the member's name, email and photo. SkillSwap compares the LinkedIn name with the profile name (order, initials and small typos are tolerated) and notes whether the emails match. LinkedIn's sign-in API does not share college or work history, so those stay self-reported. Without the LinkedIn keys, the rest of the site works normally and the button shows that verification isn't switched on yet.

## 8B. Make it a public link (Render)

1. Push the project to GitHub (section 9).
2. Go to https://dashboard.render.com → **New → Blueprint**, pick the repository. Render reads `render.yaml` and creates a web service called `skillswap` (free plan).
3. `render.yaml` connects the service to the existing Render Postgres `campushub-db` and keeps SkillSwap's tables in their own `skillswap` schema (set by `DB_SCHEMA`), so the two projects never touch each other's tables. To use Supabase instead, set `DATABASE_URL` to your Supabase Session-pooler URL in the service's **Environment** tab and delete `DB_SCHEMA`. When asked, fill in `GEMINI_API_KEY`, `LINKEDIN_CLIENT_ID` and `LINKEDIN_CLIENT_SECRET` (they can be left empty and added later). `SECRET_KEY` and `JWT_SECRET_KEY` are generated automatically.
4. Wait for the deploy to finish. Your public link is `https://skillswap-XXXX.onrender.com` (open `/api/health` to check that the database says `ok`).
5. Add `https://skillswap-XXXX.onrender.com/api/linkedin/callback` to the LinkedIn app's redirect URLs.
6. Every push to `main` redeploys automatically. Free Render services sleep after inactivity, so the first visit can take about a minute.

## 9. GitHub setup – one repository and one main branch

Your professor asked for one GitHub member/repository and no separate branches. Use this simple workflow:

1. One team member creates a GitHub repository named `SkillSwap-AI-Student-Skill-Exchange`.
2. Keep the repository on the `main` branch.
3. The repository owner uploads the extracted project.
4. Team members can work on assigned files locally. To avoid overwriting each other's work, agree who edits each file and work one-at-a-time when sharing a single working copy.
5. When another member completes a task, they can send the changed files to the repository owner, who checks and copies them into the project.
6. Before committing, the owner reviews the changed files and checks that `.env` is not included.
7. Commit and push the work to `main`.

Commands to upload the project for the first time (run in the project root):

```bash
git init
git add .
git commit -m "Initial SkillSwap project setup"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/SkillSwap-AI-Student-Skill-Exchange.git
git push -u origin main
```

Replace `YOUR-USERNAME` with the repository owner's GitHub username.

For later updates:

```bash
git status
git pull origin main
git add .
git commit -m "Describe the completed work"
git push origin main
```

Do not have two people push conflicting changes at the same time. If several people need to contribute directly to GitHub, the repository owner can invite them as collaborators; they can still work on the same `main` branch if that is the team's agreed workflow. Never share GitHub passwords or personal access tokens.

## 10. Suggested three-member work division (same main branch)

- Member 1 – Frontend: pages, styling, navigation, browser-side form handling and API calls. Main folder: `frontend/`.
- Member 2 – Backend: Flask routes, authentication, profile, skill, request, messaging and session APIs. Main file: `backend/app.py`.
- Member 3 – Database and AI: Supabase table verification, database design, matching logic, Gemini roadmap integration and testing. Coordinate model/API changes with Member 2 before editing shared backend files.

All members should understand the full workflow and test the integrated application together. Avoid simultaneous edits to `backend/app.py`.

## 11. Main API routes

- `POST /api/register`
- `POST /api/login`
- `GET /api/profile`
- `PUT /api/profile`
- `POST /api/skills`
- `DELETE /api/skills/<id>`
- `GET /api/skills/suggestions`
- `GET /api/dashboard`
- `GET /api/matches`
- `GET /api/users/<id>` (public when the profile is public)
- `POST /api/requests`
- `GET /api/requests`
- `PUT /api/requests/<id>` (accept / reject)
- `DELETE /api/requests/<id>` (cancel a pending request you sent)
- `GET /api/connections`
- `GET /api/messages/<other_user_id>` (`?after=<message_id>` for new messages only)
- `POST /api/messages/<other_user_id>`
- `GET /api/sessions`
- `POST /api/sessions`
- `PUT /api/sessions/<id>` (planned / completed / cancelled)
- `DELETE /api/sessions/<id>`
- `POST /api/reviews`
- `GET /api/users/<id>/reviews`
- `GET /api/linkedin/config`
- `POST /api/linkedin/start`
- `GET /api/linkedin/callback`
- `POST /api/linkedin/use-name`
- `POST /api/linkedin/disconnect`
- `POST /api/ai/roadmap`
- `GET /api/health`

## 12. Troubleshooting

**`python` is not recognized:** Install Python and select "Add Python to PATH", then reopen VS Code.

**`ModuleNotFoundError`:** Activate `venv` and run `python -m pip install -r requirements.txt`.

**PowerShell activation blocked:** Run the process-scoped execution policy command in section 6.

**Database connection error:** Check `.env`, connection URL, password encoding, host, port and SSL mode.

**Frontend says Failed to fetch:** Confirm Flask is running at `127.0.0.1:5000` and check the API base URL in `frontend/js/api.js`.

**LinkedIn says "redirect_uri does not match":** Add the exact callback URL (including `http`/`https` and port) to the LinkedIn app's Auth tab.

**Render deploy fails to connect to the database:** Use the Supabase *Session pooler* URL (IPv4) and keep `?sslmode=require`.

**Gemini roadmap fails:** Check the API key, quota and model availability in Google AI Studio. The app's non-AI features can be tested without a Gemini key.

## 13. Project limitations and safety

This is a learning-oriented MVP, not a production-ready public service. Messaging refreshes every few seconds rather than being truly real-time. Matching is a rule-based skill comparison, while Gemini generates the learning roadmap. Render provides HTTPS. For a larger public launch, also set exact `CORS_ORIGINS`, add rate limiting and use a migration tool such as Alembic. Never expose database passwords, JWT secrets or Gemini API keys in frontend code or GitHub.
