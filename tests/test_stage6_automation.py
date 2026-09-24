from features.material.extractor import extract_docx_content, extract_pdf_content, SUPPORTED_MATERIAL_EXTENSIONS
from features.material.knowledge_pack import source_context_for_prompt
from features.lkpd.generator import generate_lkpd_content
from features.lkpd.pdf import create_lkpd_pdf_buffer
from features.media_ajar.generator import generate_media_ajar_ai
from features.media_ajar.pptx import build_media_ajar_pptx
from features.tka.engine import available

def test_material_boundaries():
    assert {".docx",".pdf",".pptx",".ppt",".png",".jpg"}.issubset(SUPPORTED_MATERIAL_EXTENSIONS)
    assert "Tidak ada materi" in source_context_for_prompt(None)

def test_lkpd_pdf_export():
    b=create_lkpd_pdf_buffer("Matematika","Kelas 6","Rasio",{"tujuan":["A"],"ringkasan":"B","soal_1":"1","soal_2":"2","soal_3":"3","soal_4":"4","soal_5":"5","refleksi":"C"},logo_path="__missing__.png")
    assert b.getvalue().startswith(b"%PDF")

def test_media_pptx_export():
    data={"slides":[{"type":"cover","title":"Test","subtitle":"Demo","body":[]},{"type":"concept","title":"Konsep","visual_type":"concept","visual_content":"Isi","body":["A"],"speaker_notes":"Catatan"}]}
    out=build_media_ajar_pptx(data,{"kelas":"6","mapel":"Matematika"})
    assert out[:2]==b"PK"

def test_tka_boundary_is_explicit():
    assert isinstance(available(),bool)
