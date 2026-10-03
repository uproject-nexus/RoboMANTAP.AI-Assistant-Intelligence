from dataclasses import dataclass
@dataclass(frozen=True)
class StudentResultEvent:
    result_id:str; student_id:str; subject_id:str; scaled_score:float; score_scale:str; achievement_category:str; finalized_at:str
