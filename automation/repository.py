class InMemoryAutomationRepository:
    def __init__(self): self.events={}; self.deliveries={}
    def save_event(self,e): self.events[(e.event_type,e.source_id)]=e; return e
    def save_delivery(self,d,status='PENDING'): self.deliveries[d.idempotency_key]={'intent':d,'status':status}; return self.deliveries[d.idempotency_key]
    def get_delivery(self,key): return self.deliveries.get(key)
