from __future__ import annotations

import io
import re
import uuid
from datetime import datetime, timedelta, timezone

import streamlit as st
from PIL import Image

from tka_engine import (
    TKA_DEFAULT_ACTIVE_HOURS,
    TKA_DEFAULT_DURATION_SECONDS,
    TKA_TOTAL_QUESTIONS,
    backfill_tka_image_topics,
    generate_tka_30,
    get_tka_image,
    infer_tka_topic,
    list_tka_images,
    publish_tka_to_db,
    save_tka_image,
    tka_option_labels,
    validate_tka_30,
)
from tka_docx import build_tka_docx


TKA_MTS_MAPEL = ["Bahasa Indonesia", "Matematika"]
TKA_MA_WAJIB = ["Bahasa Indonesia", "Matematika", "Bahasa Inggris"]
TKA_MA_PILIHAN = [
    "Matematika Lanjutan", "Bahasa Indonesia Lanjutan", "Bahasa Inggris Lanjutan",
    "Fisika", "Kimia", "Biologi", "Ekonomi", "Sosiologi", "Geografi", "Sejarah",
    "Antropologi", "PPKn / Pendidikan Pancasila", "Bahasa Arab", "Bahasa Jerman",
    "Bahasa Prancis", "Bahasa Jepang", "Bahasa Korea", "Bahasa Mandarin",
    "Produk / Projek Kreatif dan Kewirausahaan",
]


def _now_wib():
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=7))).replace(tzinfo=None)


def _safe_code(value: str) -> str:
    return re.sub(r"[^A-Z0-9_-]", "", str(value or "").upper())[:40]


def _image_for_streamlit(data):
    if data is None:
        return None
    if isinstance(data, memoryview):
        data = data.tobytes()
    elif isinstance(data, bytearray):
        data = bytes(data)
    if isinstance(data, bytes):
        try:
            return Image.open(io.BytesIO(data))
        except Exception:
            return None
    return data


def _mapel_controls(jenjang: str) -> tuple[str, str]:
    if jenjang == "MTs":
        mapel_type = "Wajib"
        mapel = st.selectbox(
            "Mata Uji",
            TKA_MTS_MAPEL,
            key="tka_studio_mapel_mts",
            help="TKA MTs: Bahasa Indonesia dan Matematika; tidak ada mata uji pilihan.",
        )
        return mapel, mapel_type

    mapel_type = st.radio(
        "Kategori Mata Uji MA",
        ["Wajib", "Pilihan"],
        horizontal=True,
        key="tka_studio_mapel_type_ma",
        help="MA memiliki 3 mata uji wajib dan 2 mata uji pilihan.",
    )
    options = TKA_MA_WAJIB if mapel_type == "Wajib" else TKA_MA_PILIHAN
    mapel = st.selectbox("Mata Uji", options, key=f"tka_studio_mapel_ma_{mapel_type}")
    return mapel, mapel_type


@st.fragment
def render_tka_studio():
    if not st.session_state.get("_tka_topics_backfilled"):
        backfill_tka_image_topics()
        st.session_state._tka_topics_backfilled = True

    st.markdown("""
    <div class="premium-hero automation-hero">
        <div class="premium-kicker">UPN • TKA INTELLIGENCE</div>
        <div class="premium-title">🎓 RoboMANTAP <span>TKA STUDIO</span></div>
        <div class="premium-subtitle">Library gambar → paket latihan TKA → review → token → siswa</div>
        <div class="premium-pills"><span>30 SOAL PORTAL</span><span>STIMULUS IMAGE</span><span>AI GROUNDED</span><span>24 JAM</span></div>
    </div>
    """, unsafe_allow_html=True)

    teacher_name = st.text_input(
        "Nama / Identitas Guru",
        value=st.session_state.get("tka_teacher_name", "GuruMANTAP"),
        key="tka_teacher_name",
    )
    jenjang = st.selectbox(
        "Jenjang TKA",
        ["MTs", "MA"],
        key="tka_studio_jenjang",
        help="Peserta TKA pada dokumen acuan: kelas 9 untuk MTs dan kelas 12 untuk MA.",
    )
    st.caption("Target peserta: **kelas 9 MTs** atau **kelas 12 MA** sesuai juknis yang menjadi acuan desain.")
    mapel, mapel_type = _mapel_controls(jenjang)

    st.markdown("### 🖼️ Sumber Gambar / Stimulus TKA")
    source_mode = st.radio(
        "Sumber stimulus",
        ["Pilih dari Library TKA", "Upload Gambar Baru"],
        horizontal=True,
        key="tka_source_mode",
    )

    selected_ids: list[str] = []
    if source_mode == "Upload Gambar Baru":
        owner_type = st.radio(
            "Simpan sebagai",
            ["Gambar Guru", "Gambar Sistem UPN"],
            horizontal=True,
            key="tka_owner_type",
        )
        uploads = st.file_uploader(
            f"Upload 1–5 gambar stimulus untuk {mapel} • {jenjang}",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            key="tka_image_uploads",
            help="Metadata jenjang dan mapel mengikuti filter aktif. Nama file deskriptif digunakan sebagai fallback topik.",
        )
        if uploads:
            if len(uploads) > 5:
                st.warning("Maksimal 5 stimulus digunakan untuk satu paket. Hanya 5 pertama yang dipakai.")
            if st.button("💾 Simpan ke Library TKA", type="secondary", use_container_width=True, key="save_tka_images"):
                source = "SYSTEM" if owner_type == "Gambar Sistem UPN" else "GURU"
                owner = "UPN-SYSTEM" if source == "SYSTEM" else (teacher_name.strip() or "GuruMANTAP")
                saved = []
                for item in uploads[:5]:
                    topic = infer_tka_topic(item.name, jenjang, mapel)
                    image_id = save_tka_image(
                        data=item.getvalue(),
                        filename=item.name,
                        mime_type=item.type or "image/png",
                        source_type=source,
                        owner_key=owner,
                        jenjang=jenjang,
                        mapel=mapel,
                        topic=topic,
                    )
                    if image_id:
                        saved.append(image_id)
                st.session_state.tka_selected_image_ids = saved
                st.success(f"✅ {len(saved)} gambar tersimpan untuk {mapel} • {jenjang}.")
                st.rerun(scope="fragment")
        selected_ids = st.session_state.get("tka_selected_image_ids", [])[:5]
        if selected_ids:
            st.caption(f"Stimulus aktif: {len(selected_ids)} gambar")
    else:
        source_filter = st.selectbox(
            "Filter sumber library",
            ["Semua: Sistem + Gambar Saya", "Gambar Sistem", "Gambar Saya"],
            key="tka_library_source_filter",
        )
        search_term = st.text_input(
            "🔎 Cari stimulus",
            placeholder="Contoh: lingkaran, peluang, teks eksposisi, sistem pernapasan...",
            key="tka_library_search",
            help="Pencarian hanya dilakukan pada gambar yang sudah lolos filter jenjang dan mata uji.",
        )
        owner = teacher_name.strip() or "GuruMANTAP"
        source_type = None
        owner_key = owner
        if source_filter == "Gambar Sistem":
            source_type = "SYSTEM"
            owner_key = None
        elif source_filter == "Gambar Saya":
            source_type = "GURU"
        library = list_tka_images(
            source_type=source_type,
            owner_key=owner_key,
            jenjang=jenjang,
            mapel=mapel,
            search=search_term,
            limit=200,
        )
        if not library:
            st.info(f"Belum ada stimulus yang cocok untuk **{mapel} • {jenjang}** dengan filter saat ini.")
        else:
            labels = {
                str(x["image_id"]): f"{x['filename']} • {x.get('source_type','GURU')} • {x.get('topic') or infer_tka_topic(x['filename'], jenjang, mapel)}"
                for x in library
            }
            options = [str(x["image_id"]) for x in library]
            valid_previous = [
                str(x) for x in st.session_state.get("tka_library_selection", [])
                if str(x) in options
            ]
            st.session_state["tka_library_selection"] = valid_previous
            selected_ids = st.multiselect(
                f"Pilih maksimal 5 stimulus • {mapel} • {jenjang}",
                options,
                max_selections=5,
                format_func=lambda x: labels.get(x, x),
                key="tka_library_selection",
            )
            if selected_ids:
                st.caption(f"Stimulus dipilih: {len(selected_ids)}/5")
                cols = st.columns(min(5, len(selected_ids)))
                selected_lookup = {str(x["image_id"]): x for x in library}
                for col, image_id in zip(cols, selected_ids):
                    record = get_tka_image(image_id)
                    if record:
                        with col:
                            image = _image_for_streamlit(record.get("image_data"))
                            if image is not None:
                                st.image(image, caption=selected_lookup.get(image_id, record).get("filename", "Stimulus"), use_container_width=True)

    st.info(
        f"🎯 Paket latihan RoboMANTAP dibuat **tepat {TKA_TOTAL_QUESTIONS} soal**. "
        f"{jenjang} menggunakan opsi {', '.join(tka_option_labels(jenjang))}. "
        "Durasi portal default 90 menit."
    )

    if st.button("✨ GENERATE TKA 30 SOAL", type="primary", use_container_width=True, key="generate_tka_30"):
        if not selected_ids:
            st.warning("Pilih atau upload stimulus gambar terlebih dahulu.")
        else:
            with st.spinner("RoboMANTAP sedang membaca stimulus dan menyusun tepat 30 soal TKA..."):
                generated = generate_tka_30(
                    jenjang=jenjang,
                    mapel=mapel,
                    mapel_type=mapel_type,
                    image_ids=selected_ids[:5],
                )
            if len(generated) == TKA_TOTAL_QUESTIONS:
                st.session_state.tka_draft = generated
                st.session_state.tka_draft_config = {
                    "jenjang": jenjang,
                    "mapel": mapel,
                    "mapel_type": mapel_type,
                    "mode": "GURU",
                    "timer_seconds": TKA_DEFAULT_DURATION_SECONDS,
                    "active_from": None,
                    "active_until": None,
                    "active_hours": TKA_DEFAULT_ACTIVE_HOURS,
                }
                st.session_state.tka_default_code = f"TKA-{uuid.uuid4().hex[:6].upper()}"
                st.success("✅ 30 soal berhasil dibuat dan siap direview.")
            else:
                st.error("❌ AI belum menghasilkan tepat 30 soal. Paket tidak disimpan agar tidak ada TKA parsial.")

    questions = st.session_state.get("tka_draft", [])
    config = st.session_state.get("tka_draft_config", {})
    if questions:
        ok, reason = validate_tka_30(questions, config.get("jenjang", jenjang))
        if not ok:
            st.error(reason)
        else:
            st.markdown("---")
            st.markdown("### 🔎 Review TKA")
            st.caption(
                f"{config.get('jenjang')} • {config.get('mapel')} • {len(questions)} soal • "
                "Paket latihan portal • Masa aktif 24 jam"
            )
            for idx, q in enumerate(questions, 1):
                with st.expander(
                    f"{idx:02d}. {q.get('topic','TKA')} • {q.get('cognitive_level','C4')}",
                    expanded=(idx == 1),
                ):
                    st.markdown(q.get("question", ""))
                    image_id = q.get("image_id")
                    if image_id:
                        record = get_tka_image(str(image_id))
                        if record:
                            image = _image_for_streamlit(record.get("image_data"))
                            if image is not None:
                                st.image(image, caption=f"Stimulus • {record['filename']}", use_container_width=True)
                    for option in q.get("options", []):
                        st.markdown(f"- {option}")
                    st.success(f"Kunci: {q.get('correct_answer','-')}")
                    st.caption(f"Level: {q.get('cognitive_level','-')} • Topik: {q.get('topic','-')}")

            st.markdown("### 📄 Download TKA")
            try:
                docx_bytes = build_tka_docx(config, questions)
                safe_mapel = re.sub(r"[^A-Za-z0-9_-]+", "_", config.get("mapel", "TKA"))
                st.download_button(
                    "⬇️ DOWNLOAD TKA (.DOCX)",
                    data=docx_bytes,
                    file_name=f"RoboMANTAP_TKA_{config.get('jenjang','')}_{safe_mapel}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                    key="download_tka_docx",
                    on_click="ignore",
                )
            except Exception as exc:
                st.error(f"DOCX TKA gagal disiapkan: {exc}")

            st.markdown("### 🚀 Terbitkan TKA")
            code_default = st.session_state.get("tka_default_code", f"TKA-{uuid.uuid4().hex[:6].upper()}")
            code = st.text_input("Kode / Token TKA", value=code_default, key="tka_publish_code")
            st.caption(f"Aktif otomatis 24 jam: {config.get('active_from','-')} WIB → {config.get('active_until','-')} WIB")
            if st.button("🚀 TERBITKAN TKA", type="primary", use_container_width=True, key="publish_tka"):
                clean = _safe_code(code)
                if not clean:
                    st.warning("Kode TKA tidak boleh kosong.")
                else:
                    config["kode_tka"] = clean
                    publish_start = _now_wib()
                    config["active_from"] = publish_start.isoformat()
                    config["active_until"] = (publish_start + timedelta(hours=TKA_DEFAULT_ACTIVE_HOURS)).isoformat()
                    if publish_tka_to_db(clean, config, questions):
                        st.session_state.tka_last_published = clean
                        st.success(f"✅ TKA {clean} berhasil diterbitkan. Siswa dapat mengerjakannya melalui Portal TKA → By GuruMANTAP.")
                    else:
                        st.error("❌ TKA gagal diterbitkan. Pastikan database tersedia dan paket lolos validasi.")

    st.markdown("---")
    st.markdown("### 🗂️ Library Gambar TKA")
    st.caption("Gambar Guru tersimpan dan dapat dipakai ulang oleh pemiliknya; gambar Sistem menjadi aset bersama.")
    all_images = list_tka_images(limit=200)
    if all_images:
        st.dataframe(
            [
                {
                    "File": x["filename"],
                    "Sumber": x.get("source_type"),
                    "Pemilik": x.get("owner_key") or "-",
                    "Jenjang": x.get("jenjang") or "-",
                    "Mapel": x.get("mapel") or "-",
                    "Topik": x.get("topic") or infer_tka_topic(x["filename"], x.get("jenjang"), x.get("mapel")),
                }
                for x in all_images
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Library Gambar TKA belum memiliki stimulus.")
