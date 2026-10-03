from .supabase_repository import SupabaseAutomationRepository
class TKAResultAutomationDeliveryBridge:
    def __init__(self,repository,worker): self.repository=repository; self.worker=worker
    def enqueue(self,event,delivery_intent):
        existing=self.repository.get_delivery(delivery_intent.idempotency_key)
        if existing: return existing
        return self.repository.create_delivery(delivery_intent,event.event_id)
