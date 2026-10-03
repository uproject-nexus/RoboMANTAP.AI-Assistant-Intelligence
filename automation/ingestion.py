from .service import AutomationService
class TKAResultAutomationIngestion:
    def __init__(self,si_adapter,projection,automation): self.si=si_adapter; self.projection=projection; self.automation=automation
    def ingest(self,event,binding):
        r=self.si.ingest_result(event,binding)
        if r['status'] not in ('INGESTED','DUPLICATE'): return r
        evidence=self.si.evidence.get(event['result_id'])
        if not evidence: return r
        action=self.projection.project(evidence)
        ae=self.automation.create_event('NEXT_BEST_LEARNING_ACTION',action.action_id,binding.person_id,{'action':action.__dict__})
        return {'status':'READY_FOR_AUTOMATION','event':ae,'action':action}
