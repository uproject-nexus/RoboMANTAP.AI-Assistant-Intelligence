from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

class QuestionType(str, Enum): PG='PG'; MCMA='MCMA'; CATEGORY='CATEGORY'
class StimulusType(str, Enum): TEXT='TEXT'; IMAGE='IMAGE'; GRAPH='GRAPH'; TABLE='TABLE'; DIAGRAM='DIAGRAM'; MIXED='MIXED'
class ExamStatus(str, Enum): DRAFT='DRAFT'; REVIEW='REVIEW'; VALIDATED='VALIDATED'; PUBLISHED='PUBLISHED'
@dataclass(frozen=True)
class Stimulus:
    stimulus_id:str; stimulus_type:StimulusType; content:str
@dataclass(frozen=True)
class Question:
    question_id:str; number:int; question_type:QuestionType; prompt:str; options:list[str]=field(default_factory=list); stimulus_id:str|None=None; metadata:dict=field(default_factory=dict); exam_id:str|None=None
@dataclass(frozen=True)
class Exam:
    exam_id:str; title:str; jenjang:str; subject_id:str; status:ExamStatus=ExamStatus.DRAFT; duration_seconds:int=3600; timezone_name:str='Asia/Jakarta'; published_version:int|None=None
@dataclass(frozen=True)
class ExamPackage:
    package_index:int; question_ids:tuple[str,...]
@dataclass
class ExamSession:
    session_id:str; exam_id:str; starts_at:datetime; ends_at:datetime; token:str; package_count:int=5
@dataclass
class Attempt:
    attempt_id:str; session_id:str; student_id:str; package_index:int; started_at:datetime; expires_at:datetime; submitted_at:datetime|None=None; status:str='IN_PROGRESS'
@dataclass(frozen=True)
class Result:
    result_id:str; attempt_id:str; student_id:str; exam_id:str; session_id:str; subject_id:str; raw_score:float; scaled_score:float; score_scale:str; achievement_category:str; finalized_at:datetime
