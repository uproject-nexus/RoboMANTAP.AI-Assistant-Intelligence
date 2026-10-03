# TKA Web

Student UI: `/tka/student`  
Teacher/Admin Studio UI: `/tka/studio`  
OpenAPI: `/docs`

Production TKA state is persisted in PostgreSQL/Supabase. The API refuses to start its health path as healthy when the production database is unavailable. Student access uses per-student access codes provisioned by the protected Studio endpoint; session tokens are short-lived and bound to a student + TKA session.
