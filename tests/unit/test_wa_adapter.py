from wa_adapter import *
def test_adapter_idempotency():
 a=InMemoryWADeliveryAdapter({'p1'}); i=WADeliveryIntent('i1','k1','p1','hello'); x=a.deliver(i); y=a.deliver(i); assert x.status=='ACCEPTED'; assert y.status=='DUPLICATE'; assert x.provider_message_id==y.provider_message_id
