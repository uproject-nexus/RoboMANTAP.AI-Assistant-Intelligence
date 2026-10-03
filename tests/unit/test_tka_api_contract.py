from tka.models import Exam, ExamPackage, Question, QuestionType
from tka.repository import InMemoryTKARepository
from tka.studio import TKAStudioService
from tka_api.app import app
from pathlib import Path

def test_question_is_bound_to_exam_and_five_packages_are_required():
    repo=InMemoryTKARepository(); svc=TKAStudioService(repo)
    exam=Exam("e","TKA","MA","math"); svc.add_exam(exam)
    q=Question("q",1,QuestionType.PG,"x",["a","b","c","d","e"],metadata={"correct_response":"a"},exam_id="e"); svc.add_question(q,"MA","e")
    assert repo.questions["q"].exam_id=="e"
    for i in range(1,6): svc.add_package("e",ExamPackage(i,("q",)))
    assert svc.validate_publish_ready("e") is True

def test_stimulus_authoring_route_exists_and_student_payload_has_stimulus_content():
    routes={getattr(r,'path',None) for r in app.routes}
    assert '/api/tka/studio/exams/{exam_id}' in routes
    assert '/api/tka/studio/exams/{exam_id}/stimuli' in routes
    source=Path('tka_api/app.py').read_text(encoding='utf-8')
    assert "'stimuli':stimuli" in source

def test_publish_validation_requires_answer_key_and_five_indexed_packages():
    from tka.validation import validate_exam_for_publish
    exam={'jenjang':'MA'}
    q=Question('q',1,QuestionType.PG,'x',['a','b','c','d','e'],metadata={'correct_response':'a'})
    packages=[{'package_index':i,'question_ids':['q']} for i in range(1,6)]
    assert validate_exam_for_publish(exam,[q],packages,set()) is True
    bad=packages[:-1]
    try:
        validate_exam_for_publish(exam,[q],bad,set())
    except ValueError as exc:
        assert str(exc)=='FIVE_PACKAGES_REQUIRED'
    else:
        raise AssertionError('publish validation accepted fewer than five packages')


def test_stimulus_is_bound_to_exam_by_migration_contract():
    source=Path('migrations/014_tka_stimulus_exam_binding.sql').read_text(encoding='utf-8')
    assert 'add column if not exists exam_id' in source
    assert 'idx_tka_stimuli_exam' in source


def test_student_ui_sends_option_values_for_scoring():
    source=Path('tka_web/student.html').read_text(encoding='utf-8')
    assert "value=\"'+esc(q.options[i])+'\"" in source
    assert ".map(x=>x.value)" in source
    assert "Number((document.querySelector" not in source
