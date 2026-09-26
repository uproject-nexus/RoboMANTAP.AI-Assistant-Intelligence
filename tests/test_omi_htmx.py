from fastapi.testclient import TestClient

from api.application import app
from features.omi.domain import service as omi_service
from features.omi.domain.session import SESSIONS


def _quiz(option_labels=("A", "B", "C", "D")):
    options = [f"{label}. opsi {label}" for label in option_labels]
    return [
        {
            "id": i + 1,
            "question": f"Soal OMI {i + 1} $x={i}$",
            "options": options,
            "correct_answer": options[0],
        }
        for i in range(10)
    ]


def test_omi_navigation_and_setup_pages():
    client = TestClient(app)
    assert client.get("/omi").status_code == 200
    assert client.get("/omi/mts").status_code == 200
    assert client.get("/omi/ma").status_code == 200
    response = client.get("/omi/setup", params={"jenjang": "MTs (Sederajat SMP)", "mapel": "Matematika"})
    assert response.status_code == 200
    assert "Persiapan CBT OMI" in response.text
    assert "10 soal" in response.text


def test_omi_start_answer_submit_and_result(monkeypatch):
    SESSIONS.clear()
    monkeypatch.setattr(omi_service, "generate_omi_quiz_batch", lambda *args: _quiz())
    client = TestClient(app)

    response = client.post(
        "/omi/start",
        data={
            "nama": "Fulanah Test",
            "jenjang": "MTs (Sederajat SMP)",
            "mapel": "Matematika",
            "stage": "Internal",
            "selected_submateri": "Bilangan",
        },
    )
    assert response.status_code == 200
    assert "/omi/exam/" in str(response.url)
    session_id = str(response.url).rsplit("/", 1)[-1]

    exam = client.get(f"/omi/exam/{session_id}")
    assert exam.status_code == 200
    assert "Mulai Latihan OMI Sekarang" in exam.text
    assert "Tanpa batas" in exam.text
    assert "htmx.org" in exam.text

    answer = client.post(f"/omi/api/session/{session_id}/answer", data={"q_index": 0, "answer": "A. opsi A"})
    assert answer.status_code == 200

    submit = client.post(f"/omi/submit/{session_id}", follow_redirects=False)
    assert submit.status_code == 303
    assert submit.headers["location"].startswith(f"/omi/result/{session_id}")

    result = client.get(submit.headers["location"])
    assert result.status_code == 200
    assert "Skor Akhir Latihan OMI" in result.text
    assert "4" in result.text
    assert "Pembahasan Rinci" in result.text


def test_omi_hint_and_three_strike_anti_cheat(monkeypatch):
    SESSIONS.clear()
    monkeypatch.setattr(omi_service, "generate_omi_quiz_batch", lambda *args: _quiz())
    monkeypatch.setattr(omi_service, "get_omi_hint_stream", lambda *args: iter(["Petunjuk OMI"] if args else []))
    client = TestClient(app)

    response = client.post(
        "/omi/start",
        data={"nama": "Santri OMI", "jenjang": "MA (Sederajat SMA)", "mapel": "Matematika Terintegrasi", "stage": "Nasional"},
    )
    session_id = str(response.url).rsplit("/", 1)[-1]

    hint = client.post(f"/omi/api/session/{session_id}/hint", data={"q_index": 0, "attempt_input": "Saya mencoba mencari pola."})
    assert hint.status_code == 200
    assert "Petunjuk OMI" in hint.text

    warning = client.post(f"/omi/api/session/{session_id}/anti-cheat", data={"violation_count": 1, "reason": "Pindah tab"})
    assert warning.status_code == 200
    assert warning.text == "1"

    forced = client.post(f"/omi/api/session/{session_id}/anti-cheat", data={"violation_count": 3, "reason": "Pindah tab"})
    assert forced.status_code == 200
    assert forced.text == "STOP"

    result = client.get(f"/omi/result/{session_id}")
    assert result.status_code == 200
    assert "CBT OMI" in result.text


def test_omi_session_writes_explicit_monitoring_marker_and_heartbeat_position(monkeypatch):
    SESSIONS.clear()
    captured = []

    def fake_persist(**kwargs):
        captured.append(kwargs)
        return True

    monkeypatch.setattr("features.omi.domain.session.update_progress_siswa", fake_persist)
    from features.omi.domain.session import create_session, heartbeat

    sess = create_session(
        nama="Santri Monitoring",
        jenjang="MTs (Sederajat SMP)",
        mapel="Matematika",
        stage="Internal",
        selected_submateri=[],
        quiz=_quiz(),
    )
    assert captured[-1]["session_type"] == "OMI"
    assert captured[-1]["status"] == "BERJALAN"

    heartbeat(sess["session_id"], 5)
    assert captured[-1]["session_type"] == "OMI"
    assert captured[-1]["soal_sekarang"] == 6


def test_omi_exam_avoids_full_question_rerender_on_option_click():
    html = open("features/omi/web/templates/exam.html", encoding="utf-8").read()
    assert "// IMPORTANT: do not call renderQuestion here." in html
    select_block = html.split("function selectAnswer(index,opt,optIdx)", 1)[1].split("function updateNav", 1)[0]
    assert "renderQuestion(index)" not in select_block
    assert "applySelectedVisual(index,opt)" in select_block
    assert "wakeLock.request('screen')" in html
    assert "submit-processing" in html


def test_omi_initial_monitoring_write_is_lightweight_then_full(monkeypatch):
    SESSIONS.clear()
    captured = []

    def fake_persist(**kwargs):
        captured.append(kwargs)
        return True

    monkeypatch.setattr("features.omi.domain.session.update_progress_siswa", fake_persist)
    from features.omi.domain.session import create_session

    create_session(
        nama="Santri Live",
        jenjang="MA (Sederajat SMA)",
        mapel="Matematika Terintegrasi",
        stage="Internal",
        selected_submateri=[],
        quiz=_quiz(),
    )
    assert len(captured) == 2
    assert captured[0]["session_type"] == "OMI"
    assert "quiz_data_list" not in captured[0]
    assert captured[1]["session_type"] == "OMI"
    assert len(captured[1]["quiz_data_list"]) == 10


def test_omi_result_uses_quiz_custom_math_cleaner(monkeypatch):
    SESSIONS.clear()
    monkeypatch.setattr(omi_service, "generate_omi_quiz_batch", lambda *args: [
        {
            "id": 1,
            "question": r"Hitung $x^2$ dan \frac{3}{4} serta circl.",
            "options": [r"A. \frac{1}{2}", r"B. x^2", "C. 3", "D. 4"],
            "correct_answer": r"A. \frac{1}{2}",
        }
    ] * 10)
    client = TestClient(app)
    response = client.post(
        "/omi/start",
        data={"nama": "Santri Math", "jenjang": "MTs", "mapel": "Matematika", "stage": "Internal"},
    )
    session_id = str(response.url).rsplit("/", 1)[-1]
    client.post(f"/omi/api/session/{session_id}/answer", data={"q_index": 0, "answer": r"A. \frac{1}{2}"})
    submit = client.post(f"/omi/submit/{session_id}", follow_redirects=False)
    result = client.get(submit.headers["location"])
    assert "circl" not in result.text
    assert "\\frac" in result.text or "3/4" in result.text
    assert "katex" in result.text.lower()
