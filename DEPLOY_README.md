# RoboMANTAP – Happy Vibes redesign (mobile edition)

## What changed (look & feel only)
- New shared theme: `templates/_theme.html` and `templates-tka/_theme.html`
  (pastel pink/lavender, Nunito font, rounded cards, soft shadows).
  Loaded by all 6 student pages: login, exam, result for both CBT and TKA.
- Login and result pages redesigned (mascot, friendly copy "Siswi", confetti + trophy on result).
- Exam pages: same HTML/JS; only the theme include, a lobby mascot header and one button text color changed.
- Streamlit teacher dashboard: theme primary color + brand accent (hero, buttons) changed to pink.
  Dark layout and all "Benar / correct" greens were intentionally left as they were.

## Mobile comfort layer (phones are the main device)
- Big answer buttons (58px+), 16px inputs (no iOS zoom-on-focus), larger text, left-aligned questions.
- Floating bottom bar with Prev / Ragu-Ragu / Next that stays in thumb reach.
- Question navigation and submit confirmation open as bottom sheets.
- Safe-area support (notch / gesture bar), 100dvh height, pull-to-refresh disabled during the exam, light color scheme forced (no broken phone dark mode).
- Small haptic tick on answer taps (where the phone supports it).
- Streamlit dashboard/review pages: bigger buttons, 16px inputs, scrollable tabs and tables on screens under 760px.

## What did NOT change
- `main.py`, `tka_main.py`, `ai_engine.py`, `tka_engine.py`, `bank_soal_engine.py`, `student_intelligence.py`,
  `tka_*`, `vercel.json`, `requirements.txt`: untouched. Form fields, endpoints, anti-cheat, timer, scoring: untouched.

## Deploy
1. Replace the files in your GitHub repo with this folder's content (keep your existing env vars).
2. Vercel redeploys automatically. Required env vars (same as before):
   `DATABASE_URL` (or `POSTGRES_URL`), `GEMINI_API_KEY` / `GEMINI_API_KEYS`, `STREAMLIT_URL`.
3. Streamlit Cloud redeploys from the same repo (secrets stay in Streamlit settings).

## Test before students use it (5 minutes)
Student login -> start quiz -> answer, "Ragu-Ragu", open question navigation -> submit -> result page -> "Lihat Pembahasannya".
Also open the `/tka/` portal and the Streamlit dashboard once. Do this on a real phone (Android Chrome and iPhone Safari if possible).
