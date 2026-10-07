from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

import streamlit as st

from tka_engine import (
    TKA_DEFAULT_ACTIVE_HOURS,
    TKA_DEFAULT_DURATION_SECONDS,
    TKA_TOTAL_QUESTIONS,
    delete_tka_image,
    generate_tka_30,
    get_tka_image,
    list_tka_images,
    normalize_tka_jenjang,
    publish_tka_to_db,
    save_tka_image,
    tka_option_labels,
    validate_tka_30,
)


MTs_MAPELS = ("Bahasa Indonesia", "Matematika")
MA_WAJIB_MAPELS = ("Bahasa Indonesia", "Matematika", "Bahasa Inggris")
MA_PILIHAN_MAPELS = (
    "Matematika Lanjutan",
    "Bahasa Indonesia Lanjutan",
    "Bahasa Inggris Lanjutan",
    "Fisika",
    "Kimia",
    "Biologi",
    "Ekonomi",
    "Sosiologi",
    "Geografi",
    "Sejarah",
    "Antropologi",
    "PPKn/Pendidikan Pancasila",
    "Bahasa Arab",
    "Bahasa Jerman",
    "Bahasa Prancis",
    "Bahasa Jepang",
    "Bahasa Korea",
    "Bahasa Mandarin",
    "Produk/Projek Kreatif dan Kewirausahaan",
)


def _now_wib():
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=7))).replace(tzinfo=None)


def _safe_code(value: str) -> str:
    return re.sub(r"[^A-Z0-9_-]", "", str(value or "").upper())[:40]


def _mapel_options(jenjang: str) -> tuple[str, ...]:
    return MTs_MAPELS if normalize_tka_jenjang(jenjang) == "MTs" else MA_WAJIB_MAPELS + MA_PILIHAN_MAPELS


def _mapel_type(jenjang: str, mapel: str) -> str:
    if normalize_tka_jenjang(jenjang) == "MTs":
        return "Wajib"
    return "Wajib" if mapel in MA_WAJIB_MAPELS else "Pilihan"


def _fragment_rerun():
    try:
        st.rerun(scope="fragment")
    except TypeError:
        st.rerun()


def _topic_fallback(filename: str, jenjang: str, mapel: str) -> str:
    stem = re.sub(r"\.[^.]+$", "", str(filename or "")).strip()
    prefix = re.sub(r"[^a-z0-9]+", "-", f"{mapel}-{jenjang}", flags=re.I).strip("-").lower()
    slug = re.sub(r"[^a-z0-9]+", " ", stem, flags=re.I).strip()
    if prefix and slug.lower().startswith(prefix.replace("-", " ")):
        slug = slug[len(prefix.replace("-", " ")):].strip(" -")
    return re.sub(r"\s+", " ", slug).strip().title()[:160]


@st.fragment
def render_tka_studio():
    st.markdown("""
    <div class="premium-hero automation-hero">
        <div class="premium-kicker">UPN • TKA INTELLIGENCE</div>
        <div class="premium-title">🎓 RoboMANTAP <span>TKA STUDIO</span></div>
        <div class="premium-subtitle">Library stimulus → 30 soal TKA → review → token 24 jam → siswa</div>
        <div class="premium-pills"><span>30 SOAL</span><span>PG • MCMA • KATEGORI</span><span>AI GROUNDED</span><span>24 JAM</span></div>
    </div>
    """, unsafe_allow_html=True)

    teacher_name = st.text_input(
        "Nama / Identitas Guru",
        value=st.session_state.get("tka_teacher_name", "GuruMANTAP"),
        key="tka_teacher_name",
    )
    jenjang = st.selectbox("Jenjang TKA", ["MTs", "MA"], key="tka_studio_jenjang")
    target_kelas = "9" if jenjang == "MTs" else "12"
    st.info(f"🎓 Target peserta TKA {jenjang}: **Kelas {target_kelas}**.")

    mapel_options = _mapel_options(jenjang)
    current_mapel = st.session_state.get("tka_studio_mapel", mapel_options[0])
    if current_mapel not in mapel_options:
        current_mapel = mapel_options[0]
    mapel = st.selectbox("Mata Uji", list(mapel_options), index=list(mapel_options).index(current_mapel), key="tka_studio_mapel")
    mapel_type = _mapel_type(jenjang, mapel)
    st.caption(f"Kategori mata uji: **{mapel_type}**")

    st.markdown("### 🖼️ Sumber Stimulus TKA")
    source_mode = st.radio(
        "Pilih sumber stimulus",
        ["Pilih dari Library TKA", "Upload Gambar Baru"],
        horizontal=True,
        key="tka_source_mode",
    )

    selected_ids: list[str] = []
    if source_mode == "Upload Gambar Baru":
        owner_type = st.radio("Simpan sebagai", ["Gambar Guru", "Gambar Sistem UPN"], horizontal=True, key="tka_owner_type")
        uploads = st.file_uploader(
            "Upload gambar stimulus TKA (opsional, maksimal 5)",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            key="tka_image_uploads",
            help="Gambar hanya salah satu sumber stimulus. Soal TKA tetap boleh berupa teks/perhitungan tanpa gambar.",
        )
        if uploads:
            if len(uploads) > 5:
                st.warning("Maksimal 5 gambar dapat dipakai sebagai stimulus pada satu paket. Hanya 5 pertama yang digunakan.")
            if st.button("💾 Simpan ke Library TKA", type="secondary", use_container_width=True, key="save_tka_images"):
                source = "SYSTEM" if owner_type == "Gambar Sistem UPN" else "GURU"
                owner = "UPN-SYSTEM" if source == "SYSTEM" else (teacher_name.strip() or "GuruMANTAP")
                saved = []
                for item in uploads[:5]:
                    topic = _topic_fallback(item.name, jenjang, mapel)
                    image_id = save_tka_image(
                        data=item.getvalue(), filename=item.name, mime_type=item.type or "image/png",
                        source_type=source, owner_key=owner, jenjang=jenjang, mapel=mapel,
                        topic=topic,
                    )
                    if image_id:
                        saved.append(image_id)
                st.session_state.tka_selected_image_ids = saved
                st.success(f"✅ {len(saved)} gambar tersimpan di Library TKA.")
                _fragment_rerun()
        selected_ids = st.session_state.get("tka_selected_image_ids", [])[:5]
        if selected_ids:
            st.caption(f"Stimulus gambar aktif: {len(selected_ids)}")
    else:
        search = st.text_input("🔎 Cari stimulus", placeholder="Nama file, topik, kata kunci...", key="tka_library_search")
        library = list_tka_images(owner_key=teacher_name.strip() or "GuruMANTAP", jenjang=jenjang, mapel=mapel, limit=200)
        # Enforce the teacher's selected jenjang + mapel strictly. NULL metadata is not
        # allowed into a filtered result because it can belong to another subject.
        library = [
            x for x in library
            if normalize_tka_jenjang(x.get("jenjang")) == jenjang
            and str(x.get("mapel") or "").strip().casefold() == mapel.strip().casefold()
        ]
        if search.strip():
            needle = search.strip().casefold()
            library = [
                x for x in library
                if needle in str(x.get("filename") or "").casefold()
                or needle in str(x.get("topic") or "").casefold()
                or needle in " ".join(str(v) for v in (x.get("tags") or [])) .casefold()
            ]
        options = [str(x["image_id"]) for x in library]
        labels = {
            str(x["image_id"]): f"{x['filename']} • {x.get('source_type','GURU')} • {x.get('topic') or 'Tanpa topik'}"
            for x in library
        }
        selected_ids = st.multiselect(
            "Pilih maksimal 5 stimulus gambar (opsional)", options, max_selections=5,
            format_func=lambda x: labels.get(x, x), key="tka_library_selection",
        )
        if library:
            st.caption(f"Menampilkan {len(library)} gambar yang cocok untuk **{jenjang} • {mapel}**.")
            cols = st.columns(min(5, len(library)))
            for col, record in zip(cols, library[:5]):
                with col:
                    full = get_tka_image(str(record["image_id"]))
                    if full:
                        st.image(full["image_data"], caption=record["filename"], use_container_width=True)
        else:
            st.info("Belum ada gambar yang cocok dengan kombinasi jenjang dan mata uji ini. Anda tetap dapat membuat TKA tanpa gambar.")

    st.info(
        f"🎯 Paket TKA RoboMANTAP selalu **tepat {TKA_TOTAL_QUESTIONS} soal**. "
        f"Bentuk yang didukung: **PG, MCMA, Kategori**. {jenjang} menggunakan opsi {', '.join(tka_option_labels(jenjang))}. "
        "Stimulus gambar bersifat opsional. Durasi default 90 menit."
    )

    if st.button("✨ GENERATE TKA 30 SOAL", type="primary", use_container_width=True, key="generate_tka_30"):
        if not mapel.strip():
            st.warning("Mata uji harus dipilih.")
        else:
            with st.spinner("RoboMANTAP sedang menyusun tepat 30 soal TKA dengan campuran bentuk soal dan stimulus..."):
                generated = generate_tka_30(
                    jenjang=jenjang,
                    mapel=mapel.strip(),
                    mapel_type=mapel_type,
                    image_ids=selected_ids[:5],
                    auto_select_images=False,
                )
            if len(generated) == TKA_TOTAL_QUESTIONS:
                st.session_state.tka_draft = generated
                st.session_state.tka_draft_config = {
                    "jenjang": jenjang, "kelas": target_kelas, "mapel": mapel.strip(), "mapel_type": mapel_type,
                    "mode": "GURU", "timer_seconds": TKA_DEFAULT_DURATION_SECONDS,
                    "active_from": None, "active_until": None, "active_hours": TKA_DEFAULT_ACTIVE_HOURS,
                }
                st.session_state.tka_default_code = f"TKA-{uuid.uuid4().hex[:6].upper()}"
                st.success("✅ 30 soal berhasil dibuat dan siap direview.")
            else:
                st.error("❌ AI belum menghasilkan tepat 30 soal valid. Paket tidak disimpan agar tidak ada TKA parsial.")

    questions = st.session_state.get("tka_draft", [])
    config = st.session_state.get("tka_draft_config", {})
    if questions:
        ok, reason = validate_tka_30(questions, config.get("jenjang", jenjang))
        if not ok:
            st.error(reason)
        else:
            st.markdown("---")
            st.markdown("### 🔎 Review TKA")
            st.caption(f"{config.get('jenjang')} • Kelas {config.get('kelas')} • {config.get('mapel')} • {len(questions)} soal • Masa aktif 24 jam")
            for idx, q in enumerate(questions, 1):
                qtype = q.get("question_type", "PG")
                with st.expander(f"{idx:02d}. {q.get('topic','TKA')} • {qtype} • {q.get('cognitive_level','C4')}", expanded=(idx == 1)):
                    if q.get("stimulus_text"):
                        st.markdown("**Stimulus:**")
                        st.markdown(q.get("stimulus_text"))
                    image_id = q.get("image_id")
                    if image_id:
                        record = get_tka_image(str(image_id))
                        if record:
                            st.image(record["image_data"], caption=f"Stimulus • {record['filename']}", use_container_width=True)
                    st.markdown(q.get("question", ""))
                    if qtype in {"PG", "MCMA"}:
                        for option in q.get("options", []):
                            st.markdown(f"- {option}")
                        st.success(f"Kunci: {q.get('correct_answer','-')}")
                    else:
                        for n, item in enumerate(q.get("category_items", []), 1):
                            st.markdown(f"**{n}.** {item.get('statement','')}")
                            st.caption(" / ".join(item.get("options", [])))
                        st.success(f"Kunci: {q.get('correct_answers','-')}")
                    st.caption(f"Level: {q.get('cognitive_level','-')} • Topik: {q.get('topic','-')}")

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
                        st.error("❌ TKA gagal diterbitkan. Pastikan database tersedia dan 30 soal lolos validasi.")

    st.markdown("---")
    st.markdown("### 🗂️ Library Gambar TKA")
    st.caption("Gambar Guru tersimpan dan dapat dipakai ulang oleh pemiliknya; gambar Sistem menjadi aset bersama.")
    all_images = list_tka_images(limit=200)
    if all_images:
        st.dataframe([
            {
                "File": x["filename"], "Sumber": x.get("source_type"), "Pemilik": x.get("owner_key") or "-",
                "Jenjang": x.get("jenjang") or "-", "Mapel": x.get("mapel") or "-", "Topik": x.get("topic") or "-",
            }
            for x in all_images
        ], use_container_width=True, hide_index=True)
    else:
        st.info("Library Gambar TKA belum memiliki stimulus.")
