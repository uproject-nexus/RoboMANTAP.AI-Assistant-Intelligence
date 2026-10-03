from pathlib import Path
from tka_api.app import app

def test_production_routes_and_migrations_exist():
    routes={getattr(r,'path',None) for r in app.routes}
    assert '/health' in routes
    assert '/tka/student' in routes
    assert '/tka/studio' in routes
    assert '/api/tka/student/login' in routes
    assert '/api/tka/student/attempts/{attempt_id}/submit' in routes
    migrations=sorted(p.name for p in Path('migrations').glob('*.sql'))
    assert migrations[0].startswith('001_') and migrations[-1].startswith('014_')

def test_student_exam_route_has_no_answer_key_field():
    source=Path('tka_api/app.py').read_text(encoding='utf-8')
    assert "'metadata'" not in source.split("def exam_for_student",1)[1].split("@app.put",1)[0]
