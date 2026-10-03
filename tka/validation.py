from .models import QuestionType

def normalize_jenjang(v):
    u=str(v or '').strip().upper()
    if u in ('MTS','SMP'): return 'MTs'
    if u in ('MA','SMA'): return 'MA'
    raise ValueError('JENJANG_MUST_BE_MTs_OR_MA')

def option_count(jenjang): return 4 if normalize_jenjang(jenjang)=='MTs' else 5

def _required_correct_response(q):
    metadata=q.metadata or {}
    if 'correct_response' not in metadata:
        raise ValueError('CORRECT_RESPONSE_REQUIRED')
    key=metadata.get('correct_response')
    if q.question_type=='PG':
        if not isinstance(key,str) or key not in q.options:
            raise ValueError('INVALID_CORRECT_RESPONSE')
    elif q.question_type=='MCMA':
        if not isinstance(key,list) or not key or any(not isinstance(v,str) or v not in q.options for v in key) or len(set(key))!=len(key):
            raise ValueError('INVALID_CORRECT_RESPONSE')
    elif q.question_type=='CATEGORY':
        categories=metadata.get('categories')
        if not isinstance(categories,list) or not categories or any(not isinstance(v,str) or not v.strip() for v in categories):
            raise ValueError('CATEGORY_DEFINITION_REQUIRED')
        if not isinstance(key,str) or key not in categories:
            raise ValueError('INVALID_CORRECT_RESPONSE')

def validate_question(q, jenjang):
    if q.question_type not in (QuestionType.PG,QuestionType.MCMA,QuestionType.CATEGORY):
        raise ValueError('UNSUPPORTED_QUESTION_TYPE')
    if not str(q.prompt or '').strip():
        raise ValueError('PROMPT_REQUIRED')
    if q.question_type in (QuestionType.PG,QuestionType.MCMA):
        if len(q.options)!=option_count(jenjang): raise ValueError('INVALID_OPTION_COUNT')
        if any(not isinstance(v,str) or not v.strip() for v in q.options) or len(set(q.options))!=len(q.options):
            raise ValueError('INVALID_OPTIONS')
    if q.question_type==QuestionType.CATEGORY and not q.metadata.get('categories'):
        raise ValueError('CATEGORY_DEFINITION_REQUIRED')
    if q.metadata.get('matching') or q.metadata.get('type')=='MATCHING':
        raise ValueError('MATCHING_NOT_SUPPORTED')
    _required_correct_response(q)
    return True

def validate_exam_for_publish(exam, questions, packages, stimulus_ids=None):
    if not questions: raise ValueError('QUESTIONS_REQUIRED')
    seen_numbers=set()
    for q in questions:
        if q.number in seen_numbers: raise ValueError('DUPLICATE_QUESTION_NUMBER')
        seen_numbers.add(q.number)
        validate_question(q, exam['jenjang'])
        if q.stimulus_id and stimulus_ids is not None and q.stimulus_id not in stimulus_ids:
            raise ValueError('STIMULUS_NOT_FOUND')
    if len(packages)!=5: raise ValueError('FIVE_PACKAGES_REQUIRED')
    indexes={p['package_index'] for p in packages}
    if indexes != {1,2,3,4,5}: raise ValueError('PACKAGE_INDEXES_MUST_BE_1_TO_5')
    qids={q.question_id for q in questions}
    for p in packages:
        ids=list(p['question_ids'])
        if not ids: raise ValueError('PACKAGE_MUST_HAVE_QUESTIONS')
        if len(ids)!=len(set(ids)): raise ValueError('DUPLICATE_QUESTION_IN_PACKAGE')
        if not set(ids).issubset(qids): raise ValueError('PACKAGE_QUESTION_MUST_BELONG_TO_EXAM')
    return True
