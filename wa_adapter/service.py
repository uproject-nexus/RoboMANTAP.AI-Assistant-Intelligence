from .models import WADeliveryResult
class WADeliveryAdapter:
    def deliver(self,intent): raise NotImplementedError
class InMemoryWADeliveryAdapter(WADeliveryAdapter):
    def __init__(self,active_people=None): self.active_people=set(active_people or []); self.sent={}
    def deliver(self,intent):
        if intent.channel!='WHATSAPP': return WADeliveryResult(intent.intent_id,'REJECTED',reason='UNSUPPORTED_CHANNEL')
        if intent.recipient_person_id not in self.active_people: return WADeliveryResult(intent.intent_id,'REJECTED',reason='WA_IDENTITY_NOT_ACTIVE')
        if intent.idempotency_key in self.sent: return WADeliveryResult(intent.intent_id,'DUPLICATE',self.sent[intent.idempotency_key])
        pid='TEST-'+intent.idempotency_key[:16]; self.sent[intent.idempotency_key]=pid; return WADeliveryResult(intent.intent_id,'ACCEPTED',pid)
