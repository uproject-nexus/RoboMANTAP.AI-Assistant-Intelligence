from datetime import datetime, timezone
import uuid
from .models import Result
class TKAResultService:
    def __init__(self,repo): self.repo=repo
    def finalize(self,attempt,exam,correct,total):
        if attempt.status!='SUBMITTED': raise ValueError('ATTEMPT_NOT_SUBMITTED')
        for r in self.repo.results.values():
            if r.attempt_id==attempt.attempt_id: return r
        score=round((correct/total)*100,2) if total else 0.0
        cat='NEEDS_SUPPORT' if score<60 else 'DEVELOPING' if score<75 else 'PROFICIENT'
        r=Result(str(uuid.uuid4()),attempt.attempt_id,attempt.student_id,exam.exam_id,attempt.session_id,exam.subject_id,correct,score,'STANDARD_100_V1',cat,datetime.now(timezone.utc))
        self.repo.results[r.result_id]=r
        self.repo.events.setdefault(('TKA_RESULT_FINALIZED',r.result_id),r)
        return r
