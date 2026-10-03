class SupabaseAutomationRepository:
    """Persistence boundary. The Supabase client is injected; this class never creates credentials."""
    def __init__(self, client): self.client=client
    def get_delivery(self,key):
        res=(self.client.table('automation_deliveries').select('*').eq('idempotency_key',key).limit(1).execute())
        return res.data[0] if res.data else None
    def create_delivery(self,delivery,event_id):
        payload={'delivery_id':delivery.intent_id,'event_id':event_id,'recipient_person_id':delivery.recipient_person_id,'channel':delivery.channel,'idempotency_key':delivery.idempotency_key,'status':'PENDING','attempt_count':0}
        try:
            res=self.client.table('automation_deliveries').insert(payload).execute()
            return res.data[0] if res.data else payload
        except Exception:
            existing=self.get_delivery(delivery.idempotency_key)
            if existing: return existing
            raise
    def mark_sent(self,key,provider_message_id):
        return self.client.table('automation_deliveries').update({'status':'SENT','provider_message_id':provider_message_id,'sent_at':'now()'}).eq('idempotency_key',key).execute()
