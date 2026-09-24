"""Media Ajar storyboard generation service."""
from __future__ import annotations
import json
from infrastructure.ai.service import call_gemini_with_rotation, clean_json_text
from features.material.knowledge_pack import source_context_for_prompt

def generate_media_ajar_ai(*,mapel,jenjang,kelas,topik,jumlah_slide,durasi_menit,bahasa="Bahasa Indonesia",gaya="Premium UPN",mode_presentasi="Interactive",source_pack=None):
    prompt=f"""Anda adalah RoboMANTAP Media Architect. Rancang storyboard PPTX siap kelas. Mapel:{mapel}; Jenjang:{jenjang}; Kelas:{kelas}; Topik:{topik}; Jumlah slide tepat:{jumlah_slide}; Durasi:{durasi_menit} menit; Bahasa:{bahasa}; Gaya:{gaya}; Mode:{mode_presentasi}. SUMBER UTAMA:{source_context_for_prompt(source_pack)}. Gunakan sumber sebagai fakta utama; slide ringkas; variasikan konsep, visual sederhana, contoh, aktivitas, HOTS/diskusi, mini quiz, rangkuman/refleksi; speaker_notes memberi arahan guru. JSON murni: {{"deck_title":"...","deck_subtitle":"...","slides":[]}}"""
    raw=call_gemini_with_rotation(prompt,is_json=True)
    if not raw: return None
    try:
        data=json.loads(clean_json_text(raw),strict=False); slides=data.get("slides",[])
        if not isinstance(slides,list) or len(slides)!=jumlah_slide: return None
        for i,s in enumerate(slides,1): s["slide"]=i; s.setdefault("body",[]); s.setdefault("visual_type","concept"); s.setdefault("visual_content",""); s.setdefault("speaker_notes",""); s.setdefault("source_locator","")
        return data
    except Exception: return None
