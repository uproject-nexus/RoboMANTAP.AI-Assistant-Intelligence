def score_question(qtype,answer,key):
    if qtype=='PG': return 1.0 if answer==key else 0.0
    if qtype=='MCMA': return 1.0 if set(answer or [])==set(key or []) else 0.0
    if qtype=='CATEGORY': return 1.0 if answer==key else 0.0
    return 0.0
def standard_100(correct,total): return round((correct/total)*100,2) if total else 0.0
def achievement(score):
    if score < 60: return 'NEEDS_SUPPORT'
    if score < 75: return 'DEVELOPING'
    return 'PROFICIENT'
