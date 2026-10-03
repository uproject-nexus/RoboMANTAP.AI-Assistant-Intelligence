from dataclasses import dataclass
from enum import Enum
class DeliveryStatus(str,Enum): PENDING='PENDING'; PROCESSING='PROCESSING'; SENT='SENT'; FAILED='FAILED'; CANCELLED='CANCELLED'
@dataclass(frozen=True)
class AutomationEvent:
    event_id:str; event_type:str; source_id:str; person_id:str; payload:dict
@dataclass(frozen=True)
class DeliveryIntent:
    intent_id:str; idempotency_key:str; recipient_person_id:str; message_text:str; channel:str='WHATSAPP'
