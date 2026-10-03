from identity import *
def test_identity_and_unique_wa():
    r=IdentityRepository(); p=Person('p1',PersonType.STUDENT,'A'); r.add_person(p); r.add_student(StudentIdentity('s1','p1','MA')); r.bind_wa(WAIdentity('6281','p1')); assert r.wa_for_person('p1').wa_number=='6281'
    try: r.bind_wa(WAIdentity('6281','p2'))
    except ValueError as e: assert str(e)=='WA_NUMBER_ALREADY_ACTIVE'
    else: assert False
