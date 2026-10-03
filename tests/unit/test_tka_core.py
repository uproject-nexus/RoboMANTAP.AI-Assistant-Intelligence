from datetime import datetime,timezone,timedelta
from tka import *
from tka.studio import TKAStudioService
from tka.attempt import TKAAttemptService
from tka.result import TKAResultService
def test_question_contract_and_result_idempotency():
 r=InMemoryTKARepository(); s=TKAStudioService(r); e=Exam('e','TKA','MA','math'); s.add_exam(e); q=Question('q',1,QuestionType.PG,'2+2?', ['1','2','3','4','5']); s.add_question(q,'MA'); session=type('S',(),{'session_id':'ss','ends_at':datetime.now(timezone.utc)+timedelta(hours=1)})(); a=TKAAttemptService(r).start(session,'student',1); TKAAttemptService(r).submit(a.attempt_id); a= r.attempts[a.attempt_id]; rs=TKAResultService(r); x=rs.finalize(a,e,1,1); y=rs.finalize(a,e,1,1); assert x.result_id==y.result_id and x.scaled_score==100

def test_mts_has_four_options():
 r=InMemoryTKARepository(); s=TKAStudioService(r); s.add_exam(Exam('e','TKA','MTs','math')); s.add_question(Question('q',1,QuestionType.PG,'x',['a','b','c','d']),'MTs')
