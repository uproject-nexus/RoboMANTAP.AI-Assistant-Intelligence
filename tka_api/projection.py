import uuid
from .persistence import TKAProductionStore

def project_result(store: TKAProductionStore, result):
    score=float(result['scaled_score'])
    if score < 60:
        typ,priority,title='TARGETED_REMEDIATION','HIGH','Latihan terarah pada kompetensi yang belum tuntas'
    elif score < 75:
        typ,priority,title='GUIDED_PRACTICE','MEDIUM','Latihan terbimbing untuk penguatan kompetensi'
    else:
        typ,priority,title='ADVANCED_PRACTICE','NORMAL','Latihan pengayaan dan pengembangan tingkat lanjut'
    evidence_id=str(uuid.uuid4()); action_id=str(uuid.uuid4())
    with store._conn() as c, c.cursor() as cur:
        cur.execute("select si.person_id,p.display_name from student_identities si join persons p on p.person_id=si.person_id where si.student_id=%s",(result['student_id'],))
        person=cur.fetchone()
        if not person: return {'status':'IDENTITY_NOT_RESOLVED'}
        cur.execute("select evidence_id from tka_si_evidence where result_id=%s",(result['result_id'],)); existing=cur.fetchone()
        if existing: return {'status':'DUPLICATE','evidence_id':str(existing['evidence_id'])}
        cur.execute("insert into tka_si_evidence(evidence_id,result_id,student_id,subject_id,scaled_score,score_scale,achievement_category,source,finalized_at) values(%s,%s,%s,%s,%s,%s,%s,'TKA',%s)",(evidence_id,result['result_id'],result['student_id'],result['subject_id'],result['scaled_score'],result['score_scale'],result['achievement_category'],result['finalized_at']))
        payload={'subject_id':result['subject_id'],'score':score,'source':'TKA','result_id':str(result['result_id'])}
        cur.execute("insert into tka_learning_actions(action_id,evidence_id,student_id,action_type,priority,title,reason,payload) values(%s,%s,%s,%s,%s,%s,%s,%s)",(action_id,evidence_id,result['student_id'],typ,priority,title,'Berdasarkan hasil TKA terbaru',store.json(payload)))
        event_id=str(uuid.uuid4()); event_payload={'action_id':action_id,'evidence_id':evidence_id,'student_id':str(result['student_id']),'action_type':typ,'priority':priority,'title':title,'reason':'Berdasarkan hasil TKA terbaru','payload':payload}
        cur.execute("insert into automation_events(event_id,event_type,source_id,person_id,payload) values(%s,'NEXT_BEST_LEARNING_ACTION',%s,%s,%s) on conflict(event_type,source_id) do nothing returning event_id",(event_id,action_id,person['person_id'],store.json(event_payload)))
        ev=cur.fetchone()
        if ev:
            cur.execute("select wa_number from wa_identities where person_id=%s and status='ACTIVE' limit 1",(person['person_id'],)); wa=cur.fetchone()
            if wa:
                message=f"Halo {person['display_name']}! 🌸\nHasil TKA terbarumu: {score:.0f}/100.\n{title}.\nRoboMANTAP siap menemani latihan belajarmu berikutnya."
                cur.execute("insert into automation_deliveries(delivery_id,event_id,recipient_person_id,channel,idempotency_key,status,message_text) values(%s,%s,%s,'WHATSAPP',%s,'PENDING',%s) on conflict(idempotency_key) do nothing",(str(uuid.uuid4()),ev['event_id'],person['person_id'],f'NBA:{action_id}:WHATSAPP',message))
        return {'status':'PROJECTED','evidence_id':evidence_id,'action_id':action_id}
