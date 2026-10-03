from tka.models import Exam, ExamPackage, Question, QuestionType
from tka.repository import InMemoryTKARepository
from tka.studio import TKAStudioService

def test_question_is_bound_to_exam_and_five_packages_are_required():
    repo=InMemoryTKARepository(); svc=TKAStudioService(repo)
    exam=Exam("e","TKA","MA","math"); svc.add_exam(exam)
    q=Question("q",1,QuestionType.PG,"x",["a","b","c","d","e"],exam_id="e"); svc.add_question(q,"MA","e")
    assert repo.questions["q"].exam_id=="e"
    for i in range(1,6): svc.add_package("e",ExamPackage(i,("q",)))
    assert svc.validate_publish_ready("e") is True
