from automation.models import DeliveryIntent
from wa_adapter import WADeliveryIntent


def test_delivery_contract_uses_person_identity_and_idempotency():
    intent = DeliveryIntent("d1", "key-1", "person-1", "hello")
    wa = WADeliveryIntent(intent.intent_id, intent.idempotency_key, intent.recipient_person_id, intent.message_text)
    assert wa.recipient_person_id == "person-1"
    assert wa.idempotency_key == "key-1"
    assert wa.channel == "WHATSAPP"
