import os, uuid, hashlib, secrets
from datetime import datetime, timezone
from typing import Any

try:
    import psycopg2
    from psycopg2.extras import Json, RealDictCursor
except Exception:  # pragma: no cover
    psycopg2 = None
    Json = None
    RealDictCursor = None

class TKAProductionStore:
    """Small PostgreSQL persistence boundary for the TKA API.

    Uses the existing DATABASE_URL/POSTGRES_URL already used by RoboMANTAP.
    It deliberately owns only the new TKA/identity tables and never mutates
    legacy tables. The domain services remain usable with InMemoryTKARepository
    for unit tests.
    """
    def __init__(self, dsn=None):
        self.dsn = dsn or os.getenv('DATABASE_URL') or os.getenv('POSTGRES_URL')
        if not self.dsn:
            raise RuntimeError('DATABASE_URL_REQUIRED_FOR_TKA_PRODUCTION')
        if psycopg2 is None:
            raise RuntimeError('PSYCOPG2_REQUIRED_FOR_TKA_PRODUCTION')

    def _conn(self):
        return psycopg2.connect(self.dsn, cursor_factory=RealDictCursor)

    def health(self):
        with self._conn() as c, c.cursor() as cur:
            cur.execute('select 1 as ok')
            return bool(cur.fetchone()['ok'] == 1)

    def exam(self, exam_id):
        with self._conn() as c, c.cursor() as cur:
            cur.execute('select * from tka_exams where exam_id=%s', (exam_id,))
            return cur.fetchone()

    def create_exam(self, row):
        with self._conn() as c, c.cursor() as cur:
            cur.execute('''insert into tka_exams(exam_id,title,jenjang,subject_id,status,duration_seconds,timezone_name)
                           values(%s,%s,%s,%s,%s,%s,%s) returning *''',
                        (row['exam_id'],row['title'],row['jenjang'],row['subject_id'],row['status'],row['duration_seconds'],row['timezone_name']))
            return cur.fetchone()

    def update_exam_status(self, exam_id, status, version=None):
        with self._conn() as c, c.cursor() as cur:
            cur.execute('update tka_exams set status=%s,published_version=coalesce(%s,published_version) where exam_id=%s returning *', (status,version,exam_id))
            return cur.fetchone()

    def add_question(self, row):
        with self._conn() as c, c.cursor() as cur:
            cur.execute('''insert into tka_questions(question_id,exam_id,number,question_type,prompt,options,stimulus_id,metadata)
                           values(%s,%s,%s,%s,%s,%s,%s,%s) returning *''',
                        (row['question_id'],row['exam_id'],row['number'],row['question_type'],row['prompt'],Json(row['options']),row.get('stimulus_id'),Json(row.get('metadata') or {})))
            return cur.fetchone()

    def package_question_exam_mismatch(self, exam_id, question_ids):
        if not question_ids: return True
        with self._conn() as c, c.cursor() as cur:
            cur.execute('select count(*) as n from tka_questions where exam_id=%s and question_id = any(%s::uuid[])', (exam_id, question_ids))
            return int(cur.fetchone()['n']) != len(question_ids)

    def add_package(self, row):
        with self._conn() as c, c.cursor() as cur:
            cur.execute('''insert into tka_packages(package_id,exam_id,package_index,question_ids)
                           values(%s,%s,%s,%s) returning *''', (row['package_id'],row['exam_id'],row['package_index'],Json(row['question_ids'])))
            return cur.fetchone()

    def package_count(self, exam_id):
        with self._conn() as c, c.cursor() as cur:
            cur.execute('select count(*) as n from tka_packages where exam_id=%s', (exam_id,))
            return int(cur.fetchone()['n'])

    def create_session(self, row):
        with self._conn() as c, c.cursor() as cur:
            cur.execute('''insert into tka_sessions(session_id,exam_id,starts_at,ends_at,token)
                           values(%s,%s,%s,%s,%s) returning *''', tuple(row[k] for k in ('session_id','exam_id','starts_at','ends_at','token')))
            return cur.fetchone()

    def session_by_token(self, token):
        with self._conn() as c, c.cursor() as cur:
            cur.execute('select * from tka_sessions where token=%s', (token,))
            return cur.fetchone()

    def session(self, session_id):
        with self._conn() as c, c.cursor() as cur:
            cur.execute('select * from tka_sessions where session_id=%s', (session_id,))
            return cur.fetchone()

    def student_exists(self, student_id):
        with self._conn() as c, c.cursor() as cur:
            cur.execute('select 1 from student_identities where student_id=%s', (student_id,))
            return bool(cur.fetchone())

    def ensure_access_code(self, student_id, raw_code):
        digest=hashlib.sha256(raw_code.encode()).hexdigest()
        with self._conn() as c, c.cursor() as cur:
            cur.execute('''insert into tka_student_access(student_id,code_hash,active)
                           values(%s,%s,true)
                           on conflict(student_id) do update set code_hash=excluded.code_hash,active=true''',(student_id,digest))

    def valid_access(self, student_id, raw_code):
        digest=hashlib.sha256(raw_code.encode()).hexdigest()
        with self._conn() as c, c.cursor() as cur:
            cur.execute('select 1 from tka_student_access where student_id=%s and code_hash=%s and active=true',(student_id,digest))
            return bool(cur.fetchone())

    def create_student_session(self, student_id, session_id, token_hash, expires_at):
        with self._conn() as c, c.cursor() as cur:
            cur.execute('''insert into tka_student_sessions(access_session_id,student_id,session_id,token_hash,expires_at)
                           values(%s,%s,%s,%s,%s) returning access_session_id,student_id,session_id,expires_at''',
                        (str(uuid.uuid4()),student_id,session_id,token_hash,expires_at))
            return cur.fetchone()

    def student_session(self, token_hash):
        with self._conn() as c, c.cursor() as cur:
            cur.execute('select * from tka_student_sessions where token_hash=%s and expires_at>now()', (token_hash,))
            return cur.fetchone()

    def active_attempt(self, session_id, student_id):
        with self._conn() as c, c.cursor() as cur:
            cur.execute("select * from tka_attempts where session_id=%s and student_id=%s and status='IN_PROGRESS' limit 1",(session_id,student_id))
            return cur.fetchone()

    def create_attempt(self, row):
        with self._conn() as c, c.cursor() as cur:
            cur.execute('''insert into tka_attempts(attempt_id,session_id,student_id,package_index,started_at,expires_at,status)
                           values(%s,%s,%s,%s,%s,%s,%s) returning *''', tuple(row[k] for k in ('attempt_id','session_id','student_id','package_index','started_at','expires_at','status')))
            return cur.fetchone()

    def attempt(self, attempt_id):
        with self._conn() as c, c.cursor() as cur:
            cur.execute('select * from tka_attempts where attempt_id=%s',(attempt_id,))
            return cur.fetchone()

    def save_answer(self, attempt_id, question_id, answer):
        with self._conn() as c, c.cursor() as cur:
            cur.execute('''insert into tka_answers(answer_id,attempt_id,question_id,answer,revision)
                           values(%s,%s,%s,%s,1)
                           on conflict(attempt_id,question_id) do update set answer=excluded.answer,revision=tka_answers.revision+1,updated_at=now()
                           returning *''',(str(uuid.uuid4()),attempt_id,question_id,Json(answer)))
            return cur.fetchone()

    def submit(self, attempt_id):
        with self._conn() as c, c.cursor() as cur:
            cur.execute("update tka_attempts set status='SUBMITTED',submitted_at=coalesce(submitted_at,now()) where attempt_id=%s and status='IN_PROGRESS' returning *",(attempt_id,))
            row=cur.fetchone()
            if row: return row
            cur.execute('select * from tka_attempts where attempt_id=%s',(attempt_id,))
            return cur.fetchone()

    def questions_for_attempt(self, attempt_id):
        with self._conn() as c, c.cursor() as cur:
            cur.execute('''select q.* from tka_questions q join tka_attempts a on a.session_id=(select session_id from tka_attempts where attempt_id=%s)
                           where q.exam_id=(select exam_id from tka_sessions s where s.session_id=a.session_id)
                           order by q.number''',(attempt_id,))
            return cur.fetchall()

    def package_questions(self, exam_id, package_index):
        with self._conn() as c, c.cursor() as cur:
            cur.execute('select question_ids from tka_packages where exam_id=%s and package_index=%s',(exam_id,package_index))
            row=cur.fetchone()
            return list(row['question_ids']) if row else []

    def answers_for_attempt(self, attempt_id):
        with self._conn() as c, c.cursor() as cur:
            cur.execute('select question_id,answer from tka_answers where attempt_id=%s',(attempt_id,))
            return cur.fetchall()

    def result_by_attempt(self, attempt_id):
        with self._conn() as c, c.cursor() as cur:
            cur.execute('select * from tka_results where attempt_id=%s',(attempt_id,))
            return cur.fetchone()

    def create_result(self,row,event_payload):
        with self._conn() as c, c.cursor() as cur:
            cur.execute('''insert into tka_results(result_id,attempt_id,student_id,exam_id,session_id,subject_id,raw_score,scaled_score,score_scale,achievement_category,finalized_at)
                           values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           on conflict(attempt_id) do update set result_id=tka_results.result_id
                           returning *''', tuple(row[k] for k in ('result_id','attempt_id','student_id','exam_id','session_id','subject_id','raw_score','scaled_score','score_scale','achievement_category','finalized_at')))
            result=cur.fetchone()
            cur.execute('''insert into tka_events(event_id,event_type,source_id,payload) values(%s,'TKA_RESULT_FINALIZED',%s,%s) on conflict(event_type,source_id) do nothing''',(str(uuid.uuid4()),row['result_id'],Json(event_payload)))
            return result
