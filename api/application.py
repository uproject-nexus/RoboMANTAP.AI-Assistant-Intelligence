"""FastAPI composition root for RoboMANTAP CBT."""
from fastapi import FastAPI
from features.quiz.cbt_service import initialize_database
from api.routes_quiz import router as quiz_router

app = FastAPI(title="RoboMANTAP CBT Engine")
initialize_database()
app.include_router(quiz_router)

__all__ = ["app"]
