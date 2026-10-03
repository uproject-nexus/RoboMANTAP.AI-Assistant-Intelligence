import hashlib
from .models import AutomationEvent,DeliveryIntent
class AutomationService:
    def __init__(self): self.events={}; self.deliveries={}
    def create_event(self,event_type,source_id,person_id,payload):
        k=(event_type,source_id)
        if k in self.events: return self.events[k]
        e=AutomationEvent('EVT-'+hashlib.sha256(f'{event_type}:{source_id}'.encode()).hexdigest()[:20],event_type,source_id,person_id,payload); self.events[k]=e; return e
    def eligible_delivery(self,event,action,wa_active=True,automation_enabled=True,quiet_hours=False):
        if not automation_enabled or not wa_active or quiet_hours: return None
        key=hashlib.sha256(f'{event.event_id}:{action.action_id}:{event.person_id}:WHATSAPP'.encode()).hexdigest()
        if key in self.deliveries: return self.deliveries[key]
        text=f"RoboMANTAP: {action.title}. {action.reason}."
        d=DeliveryIntent('DEL-'+key[:20],key,event.person_id,text); self.deliveries[key]=d; return d
