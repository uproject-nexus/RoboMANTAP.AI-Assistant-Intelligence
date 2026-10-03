import os,requests
from .models import WADeliveryResult
class WAHTTPAdapter:
    def __init__(self,base_url=None,secret=None,timeout=15): self.base_url=(base_url or os.getenv('WA_BOT_AUTOMATION_URL','')).rstrip('/'); self.secret=secret or os.getenv('AUTOMATION_SHARED_SECRET',''); self.timeout=timeout
    def deliver(self,intent):
        if not self.base_url or not self.secret: return WADeliveryResult(intent.intent_id,'REJECTED',reason='WA_AUTOMATION_CONFIG_MISSING')
        r=requests.post(self.base_url+'/automation/deliver',json={'recipient_person_id':intent.recipient_person_id,'message_text':intent.message_text,'idempotency_key':intent.idempotency_key},headers={'X-Automation-Secret':self.secret},timeout=self.timeout)
        data=r.json() if r.content else {}
        if r.status_code==200 and data.get('status') in ('accepted','duplicate'): return WADeliveryResult(intent.intent_id,'ACCEPTED' if data.get('status')=='accepted' else 'DUPLICATE',data.get('provider_message_id'))
        return WADeliveryResult(intent.intent_id,'REJECTED',reason=data.get('reason') or data.get('status') or f'HTTP_{r.status_code}')
