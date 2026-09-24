from features.bank_soal import service
from features.bank_soal.generator import _option_labels, _option_count, _slot_list

def test_bank_service_exports():
    assert callable(service.generate_bank_soal)
    assert callable(service.build_bank_soal_docx)

def test_option_policy():
    assert _option_count("SD") == 3
    assert _option_count("SMP") == 4
    assert _option_count("SMA") == 5
    assert _option_labels("SMP") == ["A","B","C","D"]

def test_slot_list_preserves_forms():
    bp={"forms":{"PG":[1,2],"Isian":[3],"Uraian":[4]}}
    slots=_slot_list(bp)
    assert len(slots)==4
    assert [x["question_type"] for x in slots]==["PG","PG","Isian","Uraian"]


def test_docx_export_variant_structure():
    blueprint={"blueprints":[{"id":"BP-001","chapter":"Bab 1","atp":"ATP","indicator":"Indikator","forms":{"PG":[1],"Isian":[],"Uraian":[]}}],"variants_per_blueprint":2}
    questions=[
      {"blueprint_id":"BP-001","variant":1,"question_type":"PG","source_number":1,"question":"Soal V1","options":["A","B","C","D"],"correct_answer":"A","explanation":"x"},
      {"blueprint_id":"BP-001","variant":2,"question_type":"PG","source_number":1,"question":"Soal V2","options":["A","B","C","D"],"correct_answer":"A","explanation":"x"},
    ]
    data=service.build_bank_soal_docx(blueprint, questions, jenjang="SMP", mapel="Matematika", variants=2)
    assert data[:2] == b"PK"
