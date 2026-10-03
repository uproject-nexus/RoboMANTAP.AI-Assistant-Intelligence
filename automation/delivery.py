from datetime import datetime,timezone,timedelta
class DeliveryWorker:
    def __init__(self,repo,adapter,max_attempts=3): self.repo=repo; self.adapter=adapter; self.max_attempts=max_attempts
    def deliver(self,intent):
        rec=self.repo.get_delivery(intent.idempotency_key)
        if not rec: rec=self.repo.save_delivery(intent,'PENDING')
        if rec['status']=='SENT': return rec
        rec['status']='PROCESSING'; rec['attempt_count']=rec.get('attempt_count',0)+1
        try:
            result=self.adapter.deliver(intent)
            if result.status in ('ACCEPTED','DUPLICATE'):
                rec.update(status='SENT',provider_message_id=result.provider_message_id); return rec
            raise RuntimeError(result.reason or 'DELIVERY_REJECTED')
        except Exception as exc:
            rec['last_error']=str(exc)
            rec['status']='FAILED' if rec['attempt_count']>=self.max_attempts else 'PENDING'
            rec['next_retry_at']=datetime.now(timezone.utc)+timedelta(seconds=60*(2**(rec['attempt_count']-1)))
            return rec
