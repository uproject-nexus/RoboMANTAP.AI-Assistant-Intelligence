# RoboMANTAP — Mobile-first redesign package

## Direction

This version keeps the existing application modules and learning/exam workflows as the baseline, but moves the visible interface toward a bright, warm, cheerful design for students who primarily use phones. The theme is light by default; no dark base theme is forced.

### UI and learning improvements

- A new welcome hero and clearer MTs / MA entry cards.
- Warm paper backgrounds, pastel pink / apricot / mint / lavender accents, rounded cards, higher-touch targets, and responsive spacing.
- A collapsed-by-default Streamlit sidebar so the main screen has more room on mobile.
- Student Intelligence score cards reorganized into a two-by-two layout, and its navigation made horizontally scrollable where supported.
- A new **Game Lab** menu inside Student Intelligence with four self-guided mini-game arenas: Matematika, Sains Ceria, Adab & Akhlak, and Bahasa & Literasi.
- Game answers receive immediate feedback and a short explanation. Mini-game scores live in the current Streamlit session and do not change official exam results.
- App/PWA manifest colors updated to the light palette, with app icons and install metadata for the FastAPI CBT/TKA pages.
- HTML login, exam, and result pages now use a bright responsive theme. Dynamic exam content remains server-based; no exam pages or private answers are cached offline.

## Project structure

- `app.py` — main Streamlit application.
- `student_intelligence.py` — existing Student Intelligence and its new Game Lab menu integration.
- `student_games.py` — new independent mini-game interface and question bank.
- `mobile_redesign.py` — global mobile-first UI theme.
- `main.py`, `templates/` — existing FastAPI student CBT portal and pages.
- `tka_main.py`, `templates-tka/`, `tka_*.py` — existing TKA portal, templates, and logic.
- `ai_engine.py`, `bank_soal_engine.py` — existing AI, database, and question-bank logic.

## Environment variables and secrets

Use `.env.example` only as a template. Real secrets must be configured in the host's environment/secrets dashboard and **must not** be committed to GitHub or included in a shared ZIP.

Common variables referenced by the current code include:

- `GEMINI_API_KEY` or `GEMINI_API_KEYS`
- `DATABASE_URL` (or `POSTGRES_URL`)
- `STREAMLIT_URL` and `TKA_PORTAL_URL` for cross-service links
- `TEACHER_ACCESS_PIN` for the teacher portal; it is intentionally not hardcoded in source code

The real PostgreSQL/Supabase URL, Gemini key, teacher PIN, and any production credentials must be supplied by the project owner. They cannot be safely inferred from source files. The previous source-code default for the teacher PIN was removed; teacher entry will remain disabled until `TEACHER_ACCESS_PIN` is configured.

## Deployment layout

This repository contains more than one runtime. Deploy each entry point to a compatible host instead of assuming the entire repository is one single process:

### 1. Main learning app (Streamlit)

1. Push this project to the intended GitHub repository.
2. Create a Streamlit Community Cloud app and select `app.py` as the entry point.
3. Configure `GEMINI_API_KEY` (or `GEMINI_API_KEYS`) and `DATABASE_URL` in the app's Secrets settings, using valid production credentials.
4. Deploy and review application logs before sharing the URL with students.

Reference: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app

### 2. Student CBT / TKA services

The repository retains its existing `vercel.json` routing for `main.py` and `tka_main.py`. Those services use FastAPI and HTML templates; they are separate from the Streamlit process. Deploy them only after testing the actual Vercel build and each route, including login, exam submission, and template/static asset loading. Configure the same database connection in the runtime that needs it.

Reference: https://vercel.com/docs/frameworks/backend/fastapi

A code ZIP is not proof that a production host has completed a successful deployment. Verify each live service URL, database access, AI key, login, exam submission, and mobile browser behavior after hosting.

## Local run / check

With Python and the dependencies in `requirements.txt` installed:

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

To check the FastAPI CBT service separately in a compatible environment:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Do not run a public school deployment with sample/placeholder credentials. Before opening to all students, confirm the student data access rules, teacher access controls, backups, rate limits, and privacy notice.

## Mobile install note

The HTML CBT/TKA pages include a web app manifest and icon metadata intended to support “Add to Home Screen” / install flows on compatible mobile browsers over HTTPS. This does not turn server-side exams into offline exams; students still need a working connection for authentication, questions, and submission. The Streamlit app also retains its existing browser manifest integration. Confirm the install prompt on the final production domain because browser install behavior varies.

## Validation performed for this package

- Python syntax compilation checked for the main application modules.
- The mini-game question bank was checked for valid answer options.
- A live end-to-end run was **not** performed in this packaging environment because Streamlit is not installed here and production secrets/database credentials were not supplied. The application still needs a post-deployment smoke test on the target hosts.
