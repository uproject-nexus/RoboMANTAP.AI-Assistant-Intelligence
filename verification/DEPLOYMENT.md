# RoboMANTAP Production Deployment

## Release model

This release contains two existing user-facing services plus the production TKA service:

1. **Main Streamlit** — existing RoboMANTAP teacher/admin surface.
2. **Existing CBT FastAPI** — existing CBT surface; protected legacy `main.py` remains intact.
3. **TKA FastAPI** — new production TKA surface. Student UI: `/tka/student`; Teacher/Admin Studio: `/tka/studio`; OpenAPI: `/docs`.
4. **WA Bot FastAPI** — existing WhatsApp AI bot, including Supabase audit and additive authenticated automation delivery.

## Required production environment

### Main/TKA service
- `DATABASE_URL` (or `POSTGRES_URL`) — PostgreSQL/Supabase connection string.
- `TKA_STUDIO_SECRET` — long random secret used only for protected TKA Studio/admin endpoints.
- `AUTOMATION_WORKER_ENABLED=true` — enables persistent outbound automation worker.
- `WA_BOT_AUTOMATION_URL` — public/internal URL of the WA Bot service.
- `AUTOMATION_SHARED_SECRET` — must exactly match the WA Bot value.
- Existing Main App/Gemini environment variables as documented by the existing deployment.

### WA Bot
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` (or existing `SUPABASE_KEY`)
- `WA_ACCESS_TOKEN`
- `WA_PHONE_NUMBER_ID`
- `WA_VERIFY_TOKEN`
- Existing Gemini variables
- `AUTOMATION_SHARED_SECRET`

Never commit real secrets into the repository.

## Database activation

Run the additive migrations **001 through 013 in numeric order** from the `migrations/` directory.

You may use:

```bash
python scripts/apply_migrations.py
```

The script uses `DATABASE_URL`/`POSTGRES_URL` and applies only the files shipped in this release. Back up/verify the target database first. Do not change the database timezone.

Migration 011 adds per-student TKA access credentials and short-lived student sessions. Migration 012 adds explicit TKA Student Intelligence evidence/action projections. Migration 013 adds the persisted delivery message payload.

## TKA go-live sequence

1. Deploy TKA API.
2. Run `/health` and verify `persistence=postgresql`.
3. Open `/tka/studio` or `/docs` using the protected Studio secret.
4. Provision each student with an explicit access code using:
   `POST /api/tka/studio/students/access`.
5. Create the exam, questions, and exactly five package slots.
6. Move `DRAFT → REVIEW → VALIDATED`, then publish.
7. Create the exam session and distribute the generated session token to students through the school's chosen secure channel.
8. Student opens `/tka/student`, enters session token + Student ID + personal access code.
9. Verify autosave, expiry, submit and result.
10. Verify `tka_results`, `tka_events`, `tka_si_evidence`, `tka_learning_actions`, `automation_events`, and `automation_deliveries`.
11. With the worker enabled and a valid active `wa_identities` row, verify the WhatsApp delivery and `wabot_audit_logs` row.

## Identity rules

- `person_id` is the root identity.
- `student_id` / `teacher_id` are explicit identity records.
- WhatsApp is bound through `wa_identities`.
- Names, phone numbers, class and jenjang are not permanent identity keys.
- Do not bulk-create identity bindings by fuzzy name matching.

## Frozen TKA rules

- Scope: MTs and MA only.
- Types: PG, MCMA, CATEGORY.
- Matching is rejected.
- PG options: MTs=4 (A-D), MA=5 (A-E).
- Five persistent packages.
- Server-side session/attempt timing.
- Server-side package allocation and locking.
- Student responses never include answer keys or scoring metadata.
- Submit is idempotent.
- Score scale: `STANDARD_100_V1`, 0–100.

## Automation rules

`TKA_RESULT_FINALIZED → SI evidence → Next Best Learning Action → automation event → delivery PENDING → WA adapter → WA Bot → provider`.

The worker uses a database claim (`FOR UPDATE SKIP LOCKED`) so multiple worker instances do not intentionally claim the same pending delivery concurrently. Delivery retries are limited to three attempts with exponential scheduling.

## Important production limitation

Code-level verification cannot prove the availability of your real Supabase project, Meta WhatsApp credentials, Render/service URLs, DNS/TLS, or school identity data. Those are operator/environment gates, not source-code claims. The package therefore ships the scripts, migrations, health endpoint and smoke-test path needed to perform those final environment checks without modifying the protected legacy application.
