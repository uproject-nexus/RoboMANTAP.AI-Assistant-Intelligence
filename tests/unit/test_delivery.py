from automation.delivery import DeliveryWorker
from automation.repository import InMemoryAutomationRepository
from wa_adapter import InMemoryWADeliveryAdapter,WADeliveryIntent
def test_delivery_persists_and_sends():
 r=InMemoryAutomationRepository(); a=InMemoryWADeliveryAdapter({'p1'}); w=DeliveryWorker(r,a); i=WADeliveryIntent('i','k','p1','hi'); x=w.deliver(i); assert x['status']=='SENT'; assert x['provider_message_id']
