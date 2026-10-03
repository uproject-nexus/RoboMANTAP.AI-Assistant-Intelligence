from dataclasses import dataclass
@dataclass(frozen=True)
class LearningAction:
    action_id:str; student_id:str; action_type:str; priority:str; title:str; reason:str; payload:dict; source_evidence_id:str
class StudentIntelligenceProjection:
    def __init__(self): self.actions={}; self.projections={}
    def project(self,evidence):
        if evidence.get('score_scale')!='STANDARD_100_V1': raise ValueError('UNSUPPORTED_SCORE_SCALE')
        score=float(evidence['scaled_score'])
        if not 0<=score<=100: raise ValueError('INVALID_SCORE')
        self.projections[evidence['result_id']]=evidence
        if score<60: typ,pri,title='TARGETED_REMEDIATION','HIGH','Latihan terarah pada kompetensi yang belum tuntas'
        elif score<75: typ,pri,title='GUIDED_PRACTICE','MEDIUM','Latihan terbimbing untuk penguatan kompetensi'
        else: typ,pri,title='ADVANCED_PRACTICE','NORMAL','Latihan pengayaan dan pengembangan tingkat lanjut'
        action=LearningAction('NBA-'+evidence['result_id'],evidence['student_id'],typ,pri,title,'Berdasarkan hasil TKA terbaru',{'subject_id':evidence['subject_id'],'score':score},evidence['result_id'])
        self.actions[action.action_id]=action; return action
