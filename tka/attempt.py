from dataclasses import replace
from datetime import datetime, timezone
import uuid
class TKAAttemptService:
    def __init__(self,repo): self.repo=repo
    def start(self,session,student_id,package_index):
        if not 1 <= package_index <= 5: raise ValueError('INVALID_PACKAGE_INDEX')
        for a in self.repo.attempts.values():
            if a.session_id==session.session_id and a.student_id==student_id and a.status=='IN_PROGRESS': raise ValueError('ACTIVE_ATTEMPT_EXISTS')
        now=datetime.now(timezone.utc); a=__import__('tka.models',fromlist=['Attempt']).Attempt(str(uuid.uuid4()),session.session_id,student_id,package_index,now,session.ends_at)
        self.repo.attempts[a.attempt_id]=a; return a
    def save_answer(self,attempt_id,question_id,answer):
        a=self.repo.attempts[attempt_id]; now=datetime.now(timezone.utc)
        if a.status!='IN_PROGRESS' or now>=a.expires_at: raise ValueError('ATTEMPT_NOT_ACTIVE')
        self.repo.answers[(attempt_id,question_id)]=answer; return answer
    def submit(self,attempt_id):
        a=self.repo.attempts[attempt_id]
        if a.status=='SUBMITTED': return a
        a.status='SUBMITTED'; a.submitted_at=datetime.now(timezone.utc); return a
