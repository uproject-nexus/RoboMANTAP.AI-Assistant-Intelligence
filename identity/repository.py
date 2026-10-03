from .models import Person, StudentIdentity, TeacherIdentity, WAIdentity, IdentityStatus
class IdentityRepository:
    def __init__(self):
        self.people={}; self.students={}; self.teachers={}; self.wa={}
    def add_person(self,p): self.people[p.person_id]=p; return p
    def add_student(self,s): self.students[s.student_id]=s; return s
    def add_teacher(self,t): self.teachers[t.teacher_id]=t; return t
    def bind_wa(self,w):
        active=[x for x in self.wa.values() if x.wa_number==w.wa_number and x.status==IdentityStatus.ACTIVE and x.person_id!=w.person_id]
        if active: raise ValueError('WA_NUMBER_ALREADY_ACTIVE')
        self.wa[w.wa_number]=w; return w
    def person(self,person_id): return self.people.get(person_id)
    def student_for_person(self,person_id): return next((x for x in self.students.values() if x.person_id==person_id),None)
    def wa_for_person(self,person_id): return next((x for x in self.wa.values() if x.person_id==person_id and x.status==IdentityStatus.ACTIVE),None)
