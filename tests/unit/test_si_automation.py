from student_intelligence_adapter import StudentIntelligenceAdapter,StudentIdentityBinding
from student_intelligence_projection import StudentIntelligenceProjection
from automation import AutomationService,TKAResultAutomationIngestion
def test_tka_to_nba_to_automation_idempotent():
 si=StudentIntelligenceAdapter(); pr=StudentIntelligenceProjection(); au=AutomationService(); flow=TKAResultAutomationIngestion(si,pr,au); event={'result_id':'r1','subject_id':'math','scaled_score':55,'score_scale':'STANDARD_100_V1','achievement_category':'NEEDS_SUPPORT','finalized_at':'x'}; b=StudentIdentityBinding('s1','p1'); x=flow.ingest(event,b); assert x['action'].action_type=='TARGETED_REMEDIATION'; d=au.eligible_delivery(x['event'],x['action'],True,True,False); assert d.recipient_person_id=='p1'; assert au.eligible_delivery(x['event'],x['action']).idempotency_key==d.idempotency_key
