from dataclasses import dataclass
@dataclass(frozen=True)
class WADeliveryIntent:
    intent_id:str; idempotency_key:str; recipient_person_id:str; message_text:str; channel:str='WHATSAPP'
@dataclass(frozen=True)
class WADeliveryResult:
    intent_id:str; status:str; provider_message_id:str|None=None; reason:str|None=None
