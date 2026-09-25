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
    assert 'hx-post="/omi/start"' in response.text
    assert "SEDANG MEMBUAT 10 SOAL" in response.text


def test_omi_start_htmx_returns_hx_redirect(monkeypatch):
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
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )
    assert response.status_code == 204
    assert response.headers["HX-Redirect"].startswith("/omi/exam/")


def test_omi_start_validation_htmx_returns_form_fragment(monkeypatch):
    client = TestClient(app)
    response = client.post(
        "/omi/start",
        data={
            "nama": "A",
            "jenjang": "MTs (Sederajat SMP)",
            "mapel": "Matematika",
            "stage": "Internal",
        },
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert 'id="omi-start-shell"' in response.text
    assert "Nama Lengkap" in response.text
    assert "valid" in response.text


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
