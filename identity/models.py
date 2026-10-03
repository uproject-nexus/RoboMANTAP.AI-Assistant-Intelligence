from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

class PersonType(str, Enum):
    STUDENT='STUDENT'; TEACHER='TEACHER'; ADMIN='ADMIN'
class IdentityStatus(str, Enum):
    ACTIVE='ACTIVE'; INACTIVE='INACTIVE'; BLOCKED='BLOCKED'

@dataclass(frozen=True)
class Person:
    person_id: str
    person_type: PersonType
    display_name: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass(frozen=True)
class StudentIdentity:
    student_id: str
    person_id: str
    jenjang: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass(frozen=True)
class TeacherIdentity:
    teacher_id: str
    person_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass(frozen=True)
class WAIdentity:
    wa_number: str
    person_id: str
    status: IdentityStatus = IdentityStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
