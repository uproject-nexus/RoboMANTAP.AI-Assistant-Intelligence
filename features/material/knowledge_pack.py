"""Knowledge-pack orchestration: source material becomes reusable grounded context."""
from __future__ import annotations
import hashlib, os
from .extractor import *

def build_material_knowledge_pack(uploaded_files):
    files=[]
    for item in uploaded_files or []:
        name=str(getattr(item,"name","material")); ext=os.path.splitext(name)[1].lower()
        if ext not in SUPPORTED_MATERIAL_EXTENSIONS: continue
        raw=item.getvalue() if hasattr(item,"getvalue") else bytes(item)
        rec={"name":name,"extension":ext,"mime_type":SUPPORTED_MATERIAL_EXTENSIONS[ext],"size":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"content":"","locator_map":[],"visual_analysis":[]}
        try:
            if ext==".docx": rec["content"]=extract_docx_content(raw); rec["locator_map"]= [{"type":"document","locator":"paragraphs/tables"}]
            elif ext in {".pptx",".ppt"}:
                b=raw if ext==".pptx" else convert_legacy_ppt_to_pptx(raw)
                if b:
                    parsed=extract_pptx_content(b); blocks=[]
                    for s in parsed["slides"]:
                        block=f"[SLIDE {s['slide']}]\n{s['text']}"
                        if s.get("notes"): block+=f"\n[CATATAN PEMBICARA]\n{s['notes']}"
                        blocks.append(block); rec["locator_map"].append({"type":"slide","locator":s["slide"]})
                    rec["content"]=trim_text("\n\n".join(blocks),50000)
                    for im in parsed["images"][:6]:
                        a=extract_image_content(im["bytes"],im["mime_type"],f"{name}, slide {im['slide']}")
                        if a: rec["visual_analysis"].append({"locator":f"slide {im['slide']}","analysis":a})
                else: rec["content"]="Format .ppt lama diterima, tetapi konverter LibreOffice tidak tersedia. Gunakan .pptx untuk ekstraksi otomatis."
            elif ext==".pdf":
                parsed=extract_pdf_content(raw); rec["content"]=trim_text("\n\n".join(f"[HALAMAN {p['page']}]\n{p['text']}" for p in parsed["pages"]),50000); rec["locator_map"]=[{"type":"page","locator":p["page"]} for p in parsed["pages"]]
                for im in parsed["images"][:6]:
                    a=extract_image_content(im["bytes"],im["mime_type"],f"{name}, halaman {im['page']}")
                    if a: rec["visual_analysis"].append({"locator":f"halaman {im['page']}","analysis":a})
            else:
                a=extract_image_content(raw,rec["mime_type"],name); rec["content"]=a
                if a: rec["visual_analysis"].append({"locator":"image","analysis":a})
        except Exception as exc: rec["content"]=f"Ekstraksi gagal untuk {name}: {exc}"
        files.append(rec)
    blocks=[]
    for r in files:
        blocks.append(f"### FILE: {r['name']}\nFormat: {r['extension']}\nSHA-256: {r['sha256']}\nKonten:\n{r.get('content','')}")
        for v in r.get("visual_analysis",[]): blocks.append(f"Visual {v['locator']}:\n{v['analysis']}")
    return {"files":files,"file_count":len(files),"source_text":trim_text("\n\n".join(blocks),110000)}

def source_context_for_prompt(source_pack,max_chars=90000):
    if not source_pack: return "Tidak ada materi lampiran. Gunakan pengetahuan kurikulum umum secara hati-hati."
    return trim_text(source_pack.get("source_text") or "",max_chars)
