import os, time, threading, uuid
from datetime import datetime, timezone, timedelta
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor, Json
except Exception:
    psycopg2=None
from wa_adapter.http_adapter import WAHTTPAdapter
from wa_adapter.models import WADeliveryIntent

class PostgresAutomationWorker:
    def __init__(self, dsn=None, poll_seconds=10):
        self.dsn=dsn or os.getenv('DATABASE_URL') or os.getenv('POSTGRES_URL')
        self.poll_seconds=poll_seconds
        self.adapter=WAHTTPAdapter()
        self.stop_event=threading.Event()
        self.thread=None
    def _conn(self): return psycopg2.connect(self.dsn,cursor_factory=RealDictCursor)
    def _claim(self):
        with self._conn() as c, c.cursor() as cur:
            cur.execute('''with candidate as (select delivery_id from automation_deliveries where status='PENDING' and (scheduled_at is null or scheduled_at<=now()) order by created_at for update skip locked limit 1)
                           update automation_deliveries d set status='PROCESSING',attempt_count=d.attempt_count+1,updated_at=now() from candidate where d.delivery_id=candidate.delivery_id returning d.*''')
            return cur.fetchone()
    def _finish(self,row,result):
        with self._conn() as c, c.cursor() as cur:
            if result.status in ('ACCEPTED','DUPLICATE'):
                cur.execute("update automation_deliveries set status='SENT',provider_message_id=%s,sent_at=now(),updated_at=now() where delivery_id=%s and status='PROCESSING'",(result.provider_message_id,row['delivery_id']))
            else:
                attempts=int(row.get('attempt_count') or 1)
                if attempts>=3:
                    cur.execute("update automation_deliveries set status='FAILED',last_error=%s,updated_at=now() where delivery_id=%s and status='PROCESSING'",(result.reason or 'DELIVERY_REJECTED',row['delivery_id']))
                else:
                    delay=60*(2**(attempts-1))
                    cur.execute("update automation_deliveries set status='PENDING',last_error=%s,scheduled_at=now() + (%s * interval '1 second'),updated_at=now() where delivery_id=%s and status='PROCESSING'",(result.reason or 'DELIVERY_REJECTED',delay,row['delivery_id']))
    def run_once(self):
        row=self._claim()
        if not row:return False
        intent=WADeliveryIntent(str(row['delivery_id']),row['idempotency_key'],str(row['recipient_person_id']),row.get('message_text') or '',row['channel'])
        try:
            result=self.adapter.deliver(intent); self._finish(row,result)
        except Exception as e:
            class R: status='REJECTED'; provider_message_id=None; reason=str(e)
            self._finish(row,R())
        return True
    def loop(self):
        while not self.stop_event.is_set():
            try:self.run_once()
            except Exception: pass
            self.stop_event.wait(self.poll_seconds)
    def start(self):
        if not self.dsn or not os.getenv('AUTOMATION_WORKER_ENABLED','').lower() in ('1','true','yes'): return False
        if not self.adapter.base_url or not self.adapter.secret or psycopg2 is None:return False
        self.thread=threading.Thread(target=self.loop,daemon=True,name='robomantap-automation-worker'); self.thread.start(); return True
    def stop(self):
        self.stop_event.set()
