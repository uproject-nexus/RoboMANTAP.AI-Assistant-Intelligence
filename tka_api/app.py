import os, uuid, secrets
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
from pathlib import Path
from pydantic import BaseModel, Field
from tka.validation import validate_question
from tka.scoring import score_question, standard_100, achievement
from .persistence import TKAProductionStore

@asynccontextmanager
async def lifespan(app):
    if os.getenv('AUTOMATION_WORKER_ENABLED','').lower() in ('1','true','yes'):
        from automation.postgres_worker import PostgresAutomationWorker
        app.state.automation_worker=PostgresAutomationWorker(); app.state.automation_worker.start()
    try:
        yield
    finally:
        worker=getattr(app.state,'automation_worker',None)
        if worker: worker.stop()

app=FastAPI(title='RoboMANTAP TKA API',version='2.1.0',lifespan=lifespan)
STORE=None

def store():
    global STORE
    if STORE is None:
        STORE=TKAProductionStore()
    return STORE

def studio_guard(x_tka_studio_secret: str|None = Header(default=None)):
    expected=os.getenv('TKA_STUDIO_SECRET','')
    if not expected or x_tka_studio_secret!=expected: raise HTTPException(403,'STUDIO_AUTH_REQUIRED')

def student_guard(x_tka_access_token: str|None = Header(default=None)):
    if not x_tka_access_token: raise HTTPException(401,'STUDENT_AUTH_REQUIRED')
    import hashlib
    sess=store().student_session(hashlib.sha256(x_tka_access_token.encode()).hexdigest())
    if not sess: raise HTTPException(401,'INVALID_STUDENT_SESSION')
    return sess

class ExamIn(BaseModel): title:str; jenjang:str; subject_id:str; duration_seconds:int=Field(ge=60,le=86400)
class QuestionIn(BaseModel): question_id:str|None=None; number:int=Field(ge=1); question_type:str; prompt:str; options:list[str]=[]; stimulus_id:str|None=None; metadata:dict={}
class PackageIn(BaseModel): package_index:int=Field(ge=1,le=5); question_ids:list[str]
class StudentLogin(BaseModel): session_token:str; student_id:str; access_code:str
class AnswerIn(BaseModel): answer:object
class AccessProvision(BaseModel): student_id:str; access_code:str=Field(min_length=8,max_length=128)

BASE=Path(__file__).resolve().parents[1]

@app.get('/tka/student', response_class=HTMLResponse)
def student_ui():
    return (BASE/'tka_web'/'student.html').read_text(encoding='utf-8')

@app.get('/tka/studio', response_class=HTMLResponse)
def studio_ui():
    return (BASE/'tka_web'/'studio.html').read_text(encoding='utf-8')

@app.get('/health')
def health():
    try: store().health(); return {'status':'ok','service':'tka-api','persistence':'postgresql'}
    except Exception as e: raise HTTPException(503,'TKA_PERSISTENCE_UNAVAILABLE')

@app.post('/api/tka/studio/students/access', dependencies=[Depends(studio_guard)])
def provision_access(x:AccessProvision):
    if not store().student_exists(x.student_id): raise HTTPException(404,'STUDENT_NOT_FOUND')
    store().ensure_access_code(x.student_id,x.access_code); return {'status':'ACTIVE','student_id':x.student_id}

@app.post('/api/tka/student/login')
def student_login(x:StudentLogin):
    s=store().session_by_token(x.session_token)
    if not s: raise HTTPException(401,'INVALID_SESSION_TOKEN')
    now=datetime.now(timezone.utc)
    if now < s['starts_at'] or now >= s['ends_at']: raise HTTPException(409,'SESSION_NOT_ACTIVE')
    if not store().valid_access(x.student_id,x.access_code): raise HTTPException(401,'INVALID_STUDENT_CREDENTIALS')
    token=secrets.token_urlsafe(32)
    import hashlib
    store().create_student_session(x.student_id,s['session_id'],hashlib.sha256(token.encode()).hexdigest(),s['ends_at'])
    return {'access_token':token,'student_id':x.student_id,'session_id':str(s['session_id']),'expires_at':s['ends_at'].isoformat()}

@app.post('/api/tka/studio/exams', dependencies=[Depends(studio_guard)])
def create_exam(x:ExamIn):
    jen=str(x.jenjang)
    if jen not in ('MTs','MA'): raise HTTPException(422,'JENJANG_MUST_BE_MTs_OR_MA')
    row={'exam_id':str(uuid.uuid4()),'title':x.title,'jenjang':jen,'subject_id':x.subject_id,'status':'DRAFT','duration_seconds':x.duration_seconds,'timezone_name':'Asia/Jakarta'}
    return dict(store().create_exam(row))

@app.post('/api/tka/studio/exams/{exam_id}/questions', dependencies=[Depends(studio_guard)])
def add_question(exam_id:str,x:QuestionIn):
    e=store().exam(exam_id)
    if not e: raise HTTPException(404,'EXAM_NOT_FOUND')
    from tka.models import Question,QuestionType
    try: qt=QuestionType(x.question_type)
    except ValueError: raise HTTPException(422,'UNSUPPORTED_QUESTION_TYPE')
    q=Question(x.question_id or str(uuid.uuid4()),x.number,qt,x.prompt,x.options,x.stimulus_id,x.metadata,exam_id)
    try: validate_question(q,e['jenjang'])
    except ValueError as exc: raise HTTPException(422,str(exc))
    row={'question_id':q.question_id,'exam_id':exam_id,'number':q.number,'question_type':q.question_type.value,'prompt':q.prompt,'options':q.options,'stimulus_id':q.stimulus_id,'metadata':q.metadata}
    return dict(store().add_question(row))

@app.post('/api/tka/studio/exams/{exam_id}/packages', dependencies=[Depends(studio_guard)])
def add_package(exam_id:str,x:PackageIn):
    if not store().exam(exam_id): raise HTTPException(404,'EXAM_NOT_FOUND')
    if store().package_count(exam_id)>=5: raise HTTPException(409,'FIVE_PACKAGES_ALREADY_DEFINED')
    if x.package_index in []: raise HTTPException(422,'INVALID_PACKAGE_INDEX')
    if not x.question_ids: raise HTTPException(422,'PACKAGE_MUST_HAVE_QUESTIONS')
    if store().package_question_exam_mismatch(exam_id,x.question_ids): raise HTTPException(422,'PACKAGE_QUESTION_MUST_BELONG_TO_EXAM')
    row={'package_id':str(uuid.uuid4()),'exam_id':exam_id,'package_index':x.package_index,'question_ids':x.question_ids}
    try:return dict(store().add_package(row))
    except Exception as e: raise HTTPException(409,'PACKAGE_NOT_PERSISTED') from e

@app.post('/api/tka/studio/exams/{exam_id}/transition', dependencies=[Depends(studio_guard)])
def transition(exam_id:str,target:str):
    e=store().exam(exam_id)
    if not e: raise HTTPException(404,'EXAM_NOT_FOUND')
    allowed={'DRAFT':{'REVIEW'},'REVIEW':{'VALIDATED','DRAFT'},'VALIDATED':{'DRAFT'},'PUBLISHED':set()}
    if target not in allowed.get(e['status'],set()): raise HTTPException(422,'INVALID_STATUS_TRANSITION')
    return dict(store().update_exam_status(exam_id,target))

@app.post('/api/tka/studio/exams/{exam_id}/publish', dependencies=[Depends(studio_guard)])
def publish(exam_id:str):
    e=store().exam(exam_id)
    if not e: raise HTTPException(404,'EXAM_NOT_FOUND')
    if e['status']!='VALIDATED': raise HTTPException(409,'EXAM_NOT_VALIDATED')
    if store().package_count(exam_id)!=5: raise HTTPException(409,'FIVE_PACKAGES_REQUIRED')
    return dict(store().update_exam_status(exam_id,'PUBLISHED',1))

@app.post('/api/tka/studio/exams/{exam_id}/sessions', dependencies=[Depends(studio_guard)])
def create_session(exam_id:str,starts_at:datetime|None=None):
    e=store().exam(exam_id)
    if not e or e['status']!='PUBLISHED': raise HTTPException(409,'EXAM_NOT_PUBLISHED')
    start=starts_at or datetime.now(timezone.utc)
    if start.tzinfo is None: start=start.replace(tzinfo=timezone.utc)
    end=start+timedelta(seconds=int(e['duration_seconds']))
    row={'session_id':str(uuid.uuid4()),'exam_id':exam_id,'starts_at':start,'ends_at':end,'token':secrets.token_urlsafe(8)}
    return dict(store().create_session(row))

@app.post('/api/tka/student/attempts')
def start_attempt(x:StudentLogin):
    s=store().session_by_token(x.session_token)
    if not s or not store().valid_access(x.student_id,x.access_code): raise HTTPException(401,'INVALID_STUDENT_CREDENTIALS')
    now=datetime.now(timezone.utc)
    if now<s['starts_at'] or now>=s['ends_at']: raise HTTPException(409,'SESSION_NOT_ACTIVE')
    existing=store().active_attempt(s['session_id'],x.student_id)
    if existing: return dict(existing)
    # Stable server allocation: never trust a client-selected package.
    import hashlib
    package=(int(hashlib.sha256(f"{x.student_id}:{s['session_id']}".encode()).hexdigest(),16)%5)+1
    row={'attempt_id':str(uuid.uuid4()),'session_id':s['session_id'],'student_id':x.student_id,'package_index':package,'started_at':now,'expires_at':s['ends_at'],'status':'IN_PROGRESS'}
    try:return dict(store().create_attempt(row))
    except Exception: raise HTTPException(409,'ACTIVE_ATTEMPT_EXISTS')

@app.get('/api/tka/student/attempts/{attempt_id}/exam')
def exam_for_student(attempt_id:str, x_tka_access_token=Depends(student_guard)):
    a=store().attempt(attempt_id)
    if not a: raise HTTPException(404,'ATTEMPT_NOT_FOUND')
    if str(a['student_id'])!=str(x_tka_access_token['student_id']) or str(a['session_id'])!=str(x_tka_access_token['session_id']): raise HTTPException(403,'ATTEMPT_ACCESS_DENIED')
    # Access token is deliberately opaque; deployment must bind it at the reverse-proxy/session layer.
    s=store().session(a['session_id']); e=store().exam(s['exam_id'])
    qids=set(store().package_questions(e['exam_id'],a['package_index']))
    rows=[q for q in store().questions_for_attempt(attempt_id) if str(q['question_id']) in qids]
    return {'exam':{'exam_id':str(e['exam_id']),'title':e['title'],'jenjang':e['jenjang'],'subject_id':e['subject_id']},'attempt':{'attempt_id':str(a['attempt_id']),'package_index':a['package_index'],'expires_at':a['expires_at'].isoformat()},'questions':[{'question_id':str(q['question_id']),'number':q['number'],'question_type':q['question_type'],'prompt':q['prompt'],'options':q['options'],'stimulus_id':str(q['stimulus_id']) if q['stimulus_id'] else None} for q in rows]}

@app.put('/api/tka/student/attempts/{attempt_id}/answers/{question_id}')
def save_answer(attempt_id:str,question_id:str,x:AnswerIn,x_tka_access_token=Depends(student_guard)):
    a=store().attempt(attempt_id)
    if not a: raise HTTPException(404,'ATTEMPT_NOT_FOUND')
    if str(a['student_id'])!=str(x_tka_access_token['student_id']) or str(a['session_id'])!=str(x_tka_access_token['session_id']): raise HTTPException(403,'ATTEMPT_ACCESS_DENIED')
    if a['status']!='IN_PROGRESS' or datetime.now(timezone.utc)>=a['expires_at']: raise HTTPException(409,'ATTEMPT_NOT_ACTIVE')
    allowed=set(store().package_questions(store().exam(store().session(a['session_id'])['exam_id'])['exam_id'],a['package_index']))
    if question_id not in allowed: raise HTTPException(403,'QUESTION_NOT_IN_ASSIGNED_PACKAGE')
    store().save_answer(attempt_id,question_id,x.answer); return {'status':'saved'}

@app.post('/api/tka/student/attempts/{attempt_id}/submit')
def submit(attempt_id:str,x_tka_access_token=Depends(student_guard)):
    a=store().attempt(attempt_id)
    if not a: raise HTTPException(404,'ATTEMPT_NOT_FOUND')
    if str(a['student_id'])!=str(x_tka_access_token['student_id']) or str(a['session_id'])!=str(x_tka_access_token['session_id']): raise HTTPException(403,'ATTEMPT_ACCESS_DENIED')
    a=store().submit(attempt_id)
    if not a: raise HTTPException(404,'ATTEMPT_NOT_FOUND')
    existing=store().result_by_attempt(attempt_id)
    if existing: return dict(existing)
    s=store().session(a['session_id']); e=store().exam(s['exam_id']); qids=set(store().package_questions(e['exam_id'],a['package_index']))
    qs=[q for q in store().questions_for_attempt(attempt_id) if str(q['question_id']) in qids]
    answers={str(r['question_id']):r['answer'] for r in store().answers_for_attempt(attempt_id)}
    correct=0
    for q in qs:
        key=(q.get('metadata') or {}).get('correct_response')
        if key is not None and score_question(q['question_type'],answers.get(str(q['question_id'])),key): correct+=1
    scaled=standard_100(correct,len(qs)); now=datetime.now(timezone.utc); result={'result_id':str(uuid.uuid4()),'attempt_id':str(a['attempt_id']),'student_id':str(a['student_id']),'exam_id':str(e['exam_id']),'session_id':str(a['session_id']),'subject_id':e['subject_id'],'raw_score':correct,'scaled_score':scaled,'score_scale':'STANDARD_100_V1','achievement_category':achievement(scaled),'finalized_at':now}
    event={k:result[k] for k in ('result_id','attempt_id','student_id','exam_id','session_id','subject_id','raw_score','scaled_score','score_scale','achievement_category','finalized_at')}
    persisted=dict(store().create_result(result,event))
    from .projection import project_result
    project_result(store(),persisted)
    return persisted
