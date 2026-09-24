from features.monitoring.anti_cheat import normalize_state, register_violation
from features.monitoring.progress import progress_percent, answer_counts
from features.intelligence.student.analytics import build_student_profile
from features.intelligence.student.service import student_key
from features.intelligence.teacher.diagnosis import generate_individual_analysis_ai


def test_anti_cheat_stays_warn_before_three_and_stops_at_three():
    s = normalize_state(None)
    s = register_violation(s, 1, "Pindah tab")
    assert s["violation_count"] == 1 and s["detected"] is False
    s = register_violation(s, 2, "Pindah tab")
    assert s["violation_count"] == 2 and s["detected"] is False
    s = register_violation(s, 3, "Pindah tab")
    assert s["violation_count"] == 3 and s["detected"] is True


def test_progress_and_answer_counts_are_deterministic():
    assert progress_percent(5, 10) == 50.0
    assert answer_counts([True, False, None]) == {"answered": 2, "correct": 1, "wrong": 1, "total": 3}


def test_student_key_is_stable():
    assert student_key("  Ahmad   Ali ", "MA") == "ahmad ali|ma"


def test_student_profile_uses_completed_attempts_for_scores():
    sessions = [
        {"status":"SELESAI", "nilai_akhir":80, "mapel":"Matematika", "detail_jawaban":[True, False], "updated_at":"2026-01-01"},
        {"status":"BERJALAN", "nilai_akhir":100, "mapel":"Matematika", "detail_jawaban":[True, True]},
    ]
    profile = build_student_profile(sessions)
    assert profile["attempts"] == 1
    assert profile["average_score"] == 80.0


def test_teacher_diagnosis_is_importable_from_feature_layer():
    assert callable(generate_individual_analysis_ai)
