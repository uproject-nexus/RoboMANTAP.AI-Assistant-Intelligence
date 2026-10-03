import pytest
from tka.validation import validate_question
from tka.models import Question,QuestionType
def test_matching_rejected():
 with pytest.raises(ValueError): validate_question(Question('q',1,QuestionType.PG,'x',['a','b','c','d'],metadata={'matching':True}),'MTs')
def test_ma_requires_five():
 with pytest.raises(ValueError): validate_question(Question('q',1,QuestionType.PG,'x',['a','b','c','d']),'MA')

def test_answer_key_required_for_scored_question():
    with pytest.raises(ValueError, match='CORRECT_RESPONSE_REQUIRED'):
        validate_question(Question('q',1,QuestionType.PG,'x',['a','b','c','d'],metadata={}),'MTs')

def test_answer_key_must_belong_to_options():
    with pytest.raises(ValueError, match='INVALID_CORRECT_RESPONSE'):
        validate_question(Question('q',1,QuestionType.PG,'x',['a','b','c','d'],metadata={'correct_response':'e'}),'MTs')

def test_mcma_key_must_be_nonempty_subset():
    with pytest.raises(ValueError, match='INVALID_CORRECT_RESPONSE'):
        validate_question(Question('q',1,QuestionType.MCMA,'x',['a','b','c','d'],metadata={'correct_response':['e']}),'MTs')

def test_category_key_must_match_category_definition():
    with pytest.raises(ValueError, match='INVALID_CORRECT_RESPONSE'):
        validate_question(Question('q',1,QuestionType.CATEGORY,'x',metadata={'categories':['A','B'],'correct_response':'C'}),'MTs')
