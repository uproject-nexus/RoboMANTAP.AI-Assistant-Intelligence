from dataclasses import dataclass
@dataclass(frozen=True)
class StudentIdentityBinding:
    student_id:str; person_id:str
class StudentIntelligenceAdapter:
    def __init__(self): self.evidence={}; self.ingested=set()
    def ingest_result(self,event,binding):
        if not binding: return {'status':'IDENTITY_NOT_RESOLVED'}
        if event['result_id'] in self.ingested: return {'status':'DUPLICATE','result_id':event['result_id']}
        self.evidence[event['result_id']]={**event,'student_id':binding.student_id,'source':'TKA'}
        self.ingested.add(event['result_id']); return {'status':'INGESTED','result_id':event['result_id']}
