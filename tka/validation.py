from .models import QuestionType

def normalize_jenjang(v):
    u=str(v or '').strip().upper()
    if u in ('MTs','MTS','SMP'): return 'MTs'
    if u in ('MA','SMA'): return 'MA'
    raise ValueError('JENJANG_MUST_BE_MTs_OR_MA')

def option_count(jenjang): return 4 if normalize_jenjang(jenjang)=='MTs' else 5

def validate_question(q, jenjang):
    if q.question_type not in (QuestionType.PG,QuestionType.MCMA,QuestionType.CATEGORY): raise ValueError('UNSUPPORTED_QUESTION_TYPE')
    if q.question_type in (QuestionType.PG,QuestionType.MCMA) and len(q.options)!=option_count(jenjang): raise ValueError('INVALID_OPTION_COUNT')
    if q.question_type==QuestionType.CATEGORY and not q.metadata.get('categories'): raise ValueError('CATEGORY_DEFINITION_REQUIRED')
    if q.metadata.get('matching') or q.metadata.get('type')=='MATCHING': raise ValueError('MATCHING_NOT_SUPPORTED')
    return True
