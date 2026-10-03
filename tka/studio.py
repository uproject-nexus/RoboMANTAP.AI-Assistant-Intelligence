from .models import *
from .validation import validate_question
class TKAStudioService:
    def __init__(self,repo): self.repo=repo
    def add_exam(self,exam): self.repo.exams[exam.exam_id]=exam; return exam
    def add_stimulus(self,s): self.repo.stimuli[s.stimulus_id]=s; return s
    def add_question(self,q,jenjang,exam_id=None):
        validate_question(q,jenjang)
        if exam_id is not None:
            q=Question(**{**q.__dict__,'exam_id':exam_id})
        self.repo.questions[q.question_id]=q; return q
    def add_package(self,exam_id,package):
        if package.package_index not in range(1,6): raise ValueError('INVALID_PACKAGE_INDEX')
        if any(qid not in self.repo.questions for qid in package.question_ids): raise ValueError('PACKAGE_QUESTION_NOT_FOUND')
        self.repo.packages[(exam_id,package.package_index)]=package; return package
    def validate_publish_ready(self,exam_id):
        if len([1 for (eid,_),_pkg in self.repo.packages.items() if eid==exam_id]) != 5:
            raise ValueError('FIVE_PACKAGES_REQUIRED')
        return True
    def transition(self,exam_id,target):
        e=self.repo.exams[exam_id]; allowed={'DRAFT':{'REVIEW'},'REVIEW':{'VALIDATED','DRAFT'},'VALIDATED':{'PUBLISHED','DRAFT'},'PUBLISHED':set()}
        if target not in allowed[e.status.value]: raise ValueError('INVALID_STATUS_TRANSITION')
        self.repo.exams[exam_id]=Exam(**{**e.__dict__,'status':ExamStatus(target)})
        return self.repo.exams[exam_id]
