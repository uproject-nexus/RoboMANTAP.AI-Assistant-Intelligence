from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_required_architecture_exists():
    required = [
        "app.py", "main.py", "legacy/app.py", "legacy/ai_engine.py",
        "features/quiz/service.py", "features/bank_soal/service.py",
        "features/material/knowledge_pack.py", "features/intelligence/student/service.py",
        "infrastructure/ai/client.py", "infrastructure/database/connection.py",
        "infrastructure/documents/math.py", "infrastructure/documents/quiz.py",
        "infrastructure/documents/bank_soal.py",
    ]
    missing = [p for p in required if not (ROOT / p).exists()]
    assert not missing, missing

def test_entrypoints_are_thin():
    assert len((ROOT / "app.py").read_text(encoding="utf-8").splitlines()) < 20
    assert len((ROOT / "main.py").read_text(encoding="utf-8").splitlines()) < 10
