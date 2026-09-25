"""FastAPI composition root for RoboMANTAP CBT."""
from fastapi import FastAPI
from features.quiz.cbt_service import initialize_database
from api.routes_quiz import router as quiz_router
from features.omi.api.routes import router as omi_router

app = FastAPI(title="RoboMANTAP CBT Engine")
initialize_database()
app.include_router(quiz_router)
app.include_router(omi_router)

__all__ = ["app"]
