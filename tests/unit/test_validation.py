import pytest
from tka.validation import validate_question
from tka.models import Question,QuestionType
def test_matching_rejected():
 with pytest.raises(ValueError): validate_question(Question('q',1,QuestionType.PG,'x',['a','b','c','d'],metadata={'matching':True}),'MTs')
def test_ma_requires_five():
 with pytest.raises(ValueError): validate_question(Question('q',1,QuestionType.PG,'x',['a','b','c','d']),'MA')
