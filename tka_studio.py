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
    can_delete_tka_image,
    delete_tka_image_safe,
    delete_tka_images_safe_bulk,
    get_tka_images_usage_bulk,
    generate_tka_30,
    get_tka_image,
    get_tka_image_usage,
    infer_tka_topic,
    list_tka_images,
    publish_tka_to_db,
    save_tka_image,
    tka_option_labels,
    validate_tka_30,
)

from tka_docx import build_tka_docx


TKA_MTS_MAPEL = [
    "Bahasa Indonesia",
    "Matematika",
]

TKA_MA_WAJIB = [
    "Bahasa Indonesia",
    "Matematika",
    "Bahasa Inggris",
]

TKA_MA_PILIHAN = [
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
    "PPKn / Pendidikan Pancasila",
    "Bahasa Arab",
    "Bahasa Jerman",
    "Bahasa Prancis",
    "Bahasa Jepang",
    "Bahasa Korea",
    "Bahasa Mandarin",
    "Produk / Projek Kreatif dan Kewirausahaan",
]


def _now_wib():
    return (
        datetime.now(
            timezone.utc
        )
        .astimezone(
            timezone(timedelta(hours=7))
        )
        .replace(tzinfo=None)
    )


def _safe_code(value: str) -> str:
    return re.sub(
        r"[^A-Z0-9_-]",
        "",
        str(value or "").upper(),
    )[:40]


def _image_for_streamlit(data):
    if data is None:
        return None

    if isinstance(
        data,
        memoryview,
    ):
        data = data.tobytes()

    elif isinstance(
        data,
        bytearray,
    ):
        data = bytes(data)

    if isinstance(
        data,
        bytes,
    ):
        try:
            return Image.open(
                io.BytesIO(data)
            )
        except Exception:
            return None

    return data


@st.cache_data(ttl=30, max_entries=4, show_spinner=False)
def _cached_tka_library(limit: int = 200):
    return list_tka_images(limit=limit)


@st.cache_data(ttl=3600, max_entries=500, show_spinner=False)
def _cached_stimulus_preview(image_id: str, cache_key: str = ""):
    record = get_tka_image(image_id)
    if not record:
        return None

    image = _image_for_streamlit(record.get("image_data"))
    if image is None:
        return None

    try:
        image = image.copy()
        image.thumbnail((560, 420), Image.Resampling.LANCZOS)
    except Exception:
        pass

    return image


def _mapel_controls(
    jenjang: str,
) -> tuple[str, str]:

    if jenjang == "MTs":
        mapel_type = "Wajib"

        mapel = st.selectbox(
            "Mata Uji",
            TKA_MTS_MAPEL,
            key="tka_studio_mapel_mts",
            help=(
                "TKA MTs: Bahasa Indonesia dan "
                "Matematika; tidak ada mata uji pilihan."
            ),
        )

        return (
            mapel,
            mapel_type,
        )

    mapel_type = st.radio(
        "Kategori Mata Uji MA",
        ["Wajib", "Pilihan"],
        horizontal=True,
        key="tka_studio_mapel_type_ma",
        help=(
            "MA memiliki 3 mata uji wajib "
            "dan 2 mata uji pilihan."
        ),
    )

    options = (
        TKA_MA_WAJIB
        if mapel_type == "Wajib"
        else TKA_MA_PILIHAN
    )

    mapel = st.selectbox(
        "Mata Uji",
        options,
        key=f"tka_studio_mapel_ma_{mapel_type}",
    )

    return (
        mapel,
        mapel_type,
    )


@st.fragment
def render_tka_studio():

    if not st.session_state.get(
        "_tka_topics_backfilled"
    ):
        backfill_tka_image_topics()

        st.session_state._tka_topics_backfilled = True

    st.markdown(
        """
        <div class="premium-hero automation-hero">
            <div class="premium-kicker">
                UPN • TKA INTELLIGENCE
            </div>
            <div class="premium-title">
                🎓 RoboMANTAP <span>TKA STUDIO</span>
            </div>
            <div class="premium-subtitle">
                Library stimulus → paket latihan TKA →
                review → token → siswa
            </div>
            <div class="premium-pills">
                <span>30 SOAL PORTAL</span>
                <span>PG • MCMA • KATEGORI</span>
                <span>AI GROUNDED</span>
                <span>24 JAM</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    teacher_name = st.text_input(
        "Nama / Identitas Guru",
        value=st.session_state.get(
            "tka_teacher_name",
            "GuruMANTAP",
        ),
        key="tka_teacher_name",
    )

    jenjang = st.selectbox(
        "Jenjang TKA",
        ["MTs", "MA"],
        key="tka_studio_jenjang",
        help=(
            "Peserta TKA pada dokumen acuan: "
            "kelas 9 untuk MTs dan kelas 12 untuk MA."
        ),
    )

    st.caption(
        "Target peserta: **kelas 9 MTs** atau "
        "**kelas 12 MA** sesuai juknis yang "
        "menjadi acuan desain."
    )

    mapel, mapel_type = _mapel_controls(
        jenjang
    )

    st.markdown(
        "### 🖼️ Sumber Gambar / Stimulus TKA"
    )

    source_mode = st.radio(
        "Sumber stimulus",
        [
            "Pilih dari Library TKA",
            "Upload Gambar Baru",
        ],
        horizontal=True,
        key="tka_source_mode",
    )

    selected_ids: list[str] = []

    if source_mode == "Upload Gambar Baru":

        owner_type = st.radio(
            "Simpan sebagai",
            [
                "Gambar Guru",
                "Gambar Sistem UPN",
            ],
            horizontal=True,
            key="tka_owner_type",
        )

        uploads = st.file_uploader(
            f"Upload 1–5 gambar stimulus untuk "
            f"{mapel} • {jenjang}",
            type=[
                "jpg",
                "jpeg",
                "png",
                "webp",
            ],
            accept_multiple_files=True,
            key="tka_image_uploads",
            help=(
                "Metadata jenjang dan mapel "
                "mengikuti filter aktif."
            ),
        )

        if uploads:

            if len(uploads) > 5:
                st.warning(
                    "Maksimal 5 stimulus digunakan "
                    "untuk satu paket. Hanya 5 pertama "
                    "yang dipakai."
                )

            if st.button(
                "💾 Simpan ke Library TKA",
                type="secondary",
                use_container_width=True,
                key="save_tka_images",
            ):

                source = (
                    "SYSTEM"
                    if owner_type
                    == "Gambar Sistem UPN"
                    else "GURU"
                )

                owner = (
                    "UPN-SYSTEM"
                    if source == "SYSTEM"
                    else (
                        teacher_name.strip()
                        or "GuruMANTAP"
                    )
                )

                saved = []

                for item in uploads[:5]:

                    topic = infer_tka_topic(
                        item.name,
                        jenjang,
                        mapel,
                    )

                    image_id = save_tka_image(
                        data=item.getvalue(),
                        filename=item.name,
                        mime_type=(
                            item.type
                            or "image/png"
                        ),
                        source_type=source,
                        owner_key=owner,
                        jenjang=jenjang,
                        mapel=mapel,
                        topic=topic,
                    )

                    if image_id:
                        saved.append(
                            image_id
                        )

                st.session_state[
                    "tka_selected_image_ids"
                ] = saved

                st.success(
                    f"✅ {len(saved)} gambar tersimpan "
                    f"untuk {mapel} • {jenjang}."
                )

                st.rerun(
                    scope="fragment"
                )

        selected_ids = (
            st.session_state.get(
                "tka_selected_image_ids",
                [],
            )[:5]
        )

        if selected_ids:
            st.caption(
                f"Stimulus aktif: "
                f"{len(selected_ids)} gambar"
            )

    else:

        source_filter = st.selectbox(
            "Filter sumber library",
            [
                "Semua: Sistem + Gambar Saya",
                "Gambar Sistem",
                "Gambar Saya",
            ],
            key="tka_library_source_filter",
        )

        search_term = st.text_input(
            "🔎 Cari stimulus",
            placeholder=(
                "Contoh: lingkaran, peluang, "
                "teks eksposisi, sistem pernapasan..."
            ),
            key="tka_library_search",
            help=(
                "Pencarian hanya dilakukan pada gambar "
                "yang sudah lolos filter jenjang dan "
                "mata uji."
            ),
        )

        owner = (
            teacher_name.strip()
            or "GuruMANTAP"
        )

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
            st.info(
                f"Belum ada stimulus yang cocok "
                f"untuk **{mapel} • {jenjang}** "
                "dengan filter saat ini."
            )

        else:

            labels = {
                str(x["image_id"]):
                    f"{x['filename']} • "
                    f"{x.get('source_type','GURU')} • "
                    f"{x.get('topic') or infer_tka_topic(x['filename'], jenjang, mapel)}"
                for x in library
            }

            options = [
                str(x["image_id"])
                for x in library
            ]

            valid_previous = [
                str(x)
                for x in st.session_state.get(
                    "tka_library_selection",
                    [],
                )
                if str(x) in options
            ]

            st.session_state[
                "tka_library_selection"
            ] = valid_previous

            selected_ids = st.multiselect(
                f"Pilih maksimal 5 stimulus • "
                f"{mapel} • {jenjang}",
                options,
                max_selections=5,
                format_func=lambda x:
                    labels.get(x, x),
                key="tka_library_selection",
            )

            if selected_ids:

                st.caption(
                    f"Stimulus dipilih: "
                    f"{len(selected_ids)}/5"
                )

                cols = st.columns(
                    min(
                        5,
                        len(selected_ids),
                    )
                )

                selected_lookup = {
                    str(x["image_id"]): x
                    for x in library
                }

                for col, image_id in zip(
                    cols,
                    selected_ids,
                ):

                    record = get_tka_image(
                        image_id
                    )

                    if record:

                        with col:

                            image = (
                                _image_for_streamlit(
                                    record.get(
                                        "image_data"
                                    )
                                )
                            )

                            if image is not None:
                                st.image(
                                    image,
                                    caption=(
                                        selected_lookup.get(
                                            image_id,
                                            record,
                                        ).get(
                                            "filename",
                                            "Stimulus",
                                        )
                                    ),
                                    use_container_width=True,
                                )

    st.info(
        f"🎯 Paket latihan RoboMANTAP dibuat "
        f"**tepat {TKA_TOTAL_QUESTIONS} soal**. "
        f"{jenjang} menggunakan opsi "
        f"{', '.join(tka_option_labels(jenjang))} "
        "untuk PG/MCMA. "
        "Bentuk KATEGORI menggunakan respons "
        "per pernyataan. Stimulus gambar opsional. "
        "Durasi portal default 90 menit."
    )

    st.caption(
        "💡 Gambar/stimulus visual bersifat "
        "**opsional**. Soal dapat berupa hitungan "
        "biasa, teks, puisi, pidato, dialog, tabel, "
        "grafik, atau stimulus gambar sesuai "
        "kebutuhan mata uji."
    )

    if st.button(
        "✨ GENERATE TKA 30 SOAL",
        type="primary",
        use_container_width=True,
        key="generate_tka_30",
    ):

        with st.spinner(
            "RoboMANTAP sedang menyusun tepat "
            "30 soal TKA "
            "(PG • MCMA • Kategori)..."
        ):

            generated = generate_tka_30(
                jenjang=jenjang,
                mapel=mapel,
                mapel_type=mapel_type,
                image_ids=selected_ids[:5],
                auto_select_images=False,
            )

        if len(generated) == TKA_TOTAL_QUESTIONS:

            st.session_state.tka_draft = (
                generated
            )

            st.session_state.tka_draft_config = {
                "jenjang": jenjang,
                "mapel": mapel,
                "mapel_type": mapel_type,
                "mode": "GURU",
                "timer_seconds": (
                    TKA_DEFAULT_DURATION_SECONDS
                ),
                "active_from": None,
                "active_until": None,
                "active_hours": (
                    TKA_DEFAULT_ACTIVE_HOURS
                ),
            }

            st.session_state.tka_default_code = (
                f"TKA-"
                f"{uuid.uuid4().hex[:6].upper()}"
            )

            st.success(
                "✅ 30 soal berhasil dibuat "
                "dan siap direview."
            )

        else:

            st.error(
                "❌ AI belum menghasilkan tepat "
                "30 soal. Paket tidak disimpan agar "
                "tidak ada TKA parsial."
            )

    questions = st.session_state.get(
        "tka_draft",
        [],
    )

    config = st.session_state.get(
        "tka_draft_config",
        {},
    )

    if questions:

        ok, reason = validate_tka_30(
            questions,
            config.get(
                "jenjang",
                jenjang,
            ),
        )

        if not ok:
            st.error(reason)

        else:

            st.markdown("---")
            st.markdown(
                "### 🔎 Review TKA"
            )

            st.caption(
                f"{config.get('jenjang')} • "
                f"{config.get('mapel')} • "
                f"{len(questions)} soal • "
                "Paket latihan portal • "
                "Masa aktif 24 jam"
            )

            for idx, q in enumerate(
                questions,
                1,
            ):

                with st.expander(
                    f"{idx:02d}. "
                    f"{q.get('topic','TKA')} • "
                    f"{q.get('cognitive_level','C4')}",
                    expanded=(
                        idx == 1
                    ),
                ):

                    qtype = str(
                        q.get(
                            "question_type"
                        )
                        or "PG"
                    ).upper()

                    type_label = {
                        "PG": (
                            "Pilihan Ganda"
                        ),
                        "MCMA": (
                            "Pilihan Ganda "
                            "Kompleks • MCMA"
                        ),
                        "KATEGORI": (
                            "Pilihan Ganda "
                            "Kompleks • Kategori"
                        ),
                    }.get(
                        qtype,
                        qtype,
                    )

                    st.markdown(
                        f"**Bentuk:** "
                        f"{type_label}"
                    )

                    if q.get(
                        "stimulus_text"
                    ):
                        st.markdown(
                            "**Stimulus:**\n\n"
                            f"{q.get('stimulus_text')}"
                        )

                    st.markdown(
                        q.get(
                            "question",
                            "",
                        )
                    )

                    image_id = q.get(
                        "image_id"
                    )

                    if image_id:

                        record = get_tka_image(
                            str(image_id)
                        )

                        if record:

                            image = (
                                _image_for_streamlit(
                                    record.get(
                                        "image_data"
                                    )
                                )
                            )

                            if image is not None:
                                st.image(
                                    image,
                                    caption=(
                                        "Stimulus • "
                                        f"{record['filename']}"
                                    ),
                                    use_container_width=True,
                                )

                    if qtype in {
                        "PG",
                        "MCMA",
                    }:

                        for option in q.get(
                            "options",
                            [],
                        ):
                            st.markdown(
                                f"- {option}"
                            )

                        st.success(
                            f"Kunci: "
                            f"{q.get('correct_answer','-')}"
                        )

                    else:

                        for pos, category in enumerate(
                            q.get(
                                "category_items",
                                [],
                            ),
                            1,
                        ):

                            st.markdown(
                                f"**{pos}.** "
                                f"{category.get('statement','')}"
                            )

                            st.caption(
                                "Respons: "
                                + " / ".join(
                                    str(x)
                                    for x in (
                                        category.get(
                                            "options"
                                        )
                                        or []
                                    )
                                )
                            )

                        st.success(
                            "Kunci kategori: "
                            + " | ".join(
                                str(x)
                                for x in (
                                    q.get(
                                        "correct_answers"
                                    )
                                    or []
                                )
                            )
                        )

                    st.caption(
                        f"Level: "
                        f"{q.get('cognitive_level','-')} "
                        f"• Topik: "
                        f"{q.get('topic','-')}"
                    )

            st.markdown(
                "### 📄 Download TKA"
            )

            try:

                docx_bytes = build_tka_docx(
                    config,
                    questions,
                )

                safe_mapel = re.sub(
                    r"[^A-Za-z0-9_-]+",
                    "_",
                    config.get(
                        "mapel",
                        "TKA",
                    ),
                )

                st.download_button(
                    "⬇️ DOWNLOAD TKA (.DOCX)",
                    data=docx_bytes,
                    file_name=(
                        f"RoboMANTAP_TKA_"
                        f"{config.get('jenjang','')}_"
                        f"{safe_mapel}.docx"
                    ),
                    mime=(
                        "application/vnd.openxmlformats-"
                        "officedocument.wordprocessingml.document"
                    ),
                    use_container_width=True,
                    key="download_tka_docx",
                    on_click="ignore",
                )

            except Exception as exc:

                st.error(
                    f"DOCX TKA gagal disiapkan: {exc}"
                )

            st.markdown(
                "### 🚀 Terbitkan TKA"
            )

            code_default = st.session_state.get(
                "tka_default_code",
                f"TKA-{uuid.uuid4().hex[:6].upper()}",
            )

            code = st.text_input(
                "Kode / Token TKA",
                value=code_default,
                key="tka_publish_code",
            )

            st.caption(
                f"Aktif otomatis 24 jam: "
                f"{config.get('active_from','-')} WIB "
                f"→ "
                f"{config.get('active_until','-')} WIB"
            )

            if st.button(
                "🚀 TERBITKAN TKA",
                type="primary",
                use_container_width=True,
                key="publish_tka",
            ):

                clean = _safe_code(
                    code
                )

                if not clean:

                    st.warning(
                        "Kode TKA tidak boleh kosong."
                    )

                else:

                    config["kode_tka"] = clean

                    publish_start = _now_wib()

                    config[
                        "active_from"
                    ] = publish_start.isoformat()

                    config[
                        "active_until"
                    ] = (
                        publish_start
                        + timedelta(
                            hours=TKA_DEFAULT_ACTIVE_HOURS
                        )
                    ).isoformat()

                    if publish_tka_to_db(
                        clean,
                        config,
                        questions,
                    ):

                        st.session_state[
                            "tka_last_published"
                        ] = clean

                        st.success(
                            f"✅ TKA {clean} berhasil "
                            "diterbitkan. Siswa dapat "
                            "mengerjakannya melalui "
                            "Portal TKA → By GuruMANTAP."
                        )

                    else:

                        st.error(
                            "❌ TKA gagal diterbitkan. "
                            "Pastikan database tersedia "
                            "dan paket lolos validasi."
                        )

    # =========================================================
    # TKA IMAGE LIBRARY
    # =========================================================

    st.markdown("---")
    st.markdown("### 🗂️ Library Gambar TKA")
    st.caption(
        "Kelola stimulus dengan filter metadata yang ringan. "
        "Preview hanya dirender untuk halaman yang sedang dibuka; "
        "gambar yang sudah dipakai TKA aktif akan meminta konfirmasi "
        "dan tetap dilindungi sampai masa aktifnya selesai."
    )

    all_images = _cached_tka_library(200)

    if all_images:
        st.dataframe(
            [
                {
                    "File": x["filename"],
                    "Sumber": x.get("source_type"),
                    "Pemilik": x.get("owner_key") or "-",
                    "Jenjang": x.get("jenjang") or "-",
                    "Mapel": x.get("mapel") or "-",
                    "Topik": (
                        x.get("topic")
                        or infer_tka_topic(
                            x["filename"],
                            x.get("jenjang"),
                            x.get("mapel"),
                        )
                    ),
                }
                for x in all_images
            ],
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("#### 🗑️ Kelola Stimulus")
        st.caption(
            "Mode kelola dibuat ringan: daftar di bawah hanya memuat metadata, "
            "bukan me-render ulang seluruh gambar. Preview gambar hanya dimuat "
            "saat Anda memilih satu stimulus."
        )

        current_teacher = teacher_name.strip() or "GuruMANTAP"

        page_size = 50
        page_count = max(1, (len(all_images) + page_size - 1) // page_size)
        page_options = list(range(1, page_count + 1))
        page = st.selectbox(
            "Halaman stimulus",
            page_options,
            key="tka_manage_library_page",
            format_func=lambda n: (
                f"Halaman {n} • "
                f"{min(page_size, len(all_images) - (n-1)*page_size)} gambar"
            ),
        )

        start = (page - 1) * page_size
        page_images = all_images[start:start + page_size]

        # ---------------------------------------------------------------
        # HAPUS MASSAL: checkbox berada di dalam form supaya memilih banyak
        # gambar tidak memicu rerun setiap kali checkbox diklik.
        # ---------------------------------------------------------------
        batch_state_key = "tka_batch_delete_pending"
        batch_pending = st.session_state.get(batch_state_key)

        st.markdown("##### ☑️ Pilih Banyak untuk Dihapus")
        st.caption(
            "Centang beberapa stimulus lalu klik 'Periksa & Siapkan Penghapusan'. "
            "Perubahan checkbox tidak menjalankan proses berat sampai tombol form ditekan."
        )

        with st.form("tka_bulk_delete_form", clear_on_submit=False):
            selected_batch_ids = []
            selected_batch_items = {}

            for record in page_images:
                image_id = str(record.get("image_id") or "")
                if not image_id:
                    continue
                source_type = str(record.get("source_type") or "GURU").upper()
                owner_key = str(record.get("owner_key") or "")
                can_select = (
                    source_type == "SYSTEM"
                    or (source_type == "GURU" and owner_key.lower() == current_teacher.lower())
                )
                if not can_select:
                    continue

                label = str(record.get("filename") or image_id)
                if st.checkbox(
                    label,
                    key=f"tka_bulk_select_{image_id}",
                ):
                    selected_batch_ids.append(image_id)
                    selected_batch_items[image_id] = {
                        "image_id": image_id,
                        "owner_key": None if source_type == "SYSTEM" else current_teacher,
                        "allow_system": source_type == "SYSTEM",
                    }

            bulk_submit = st.form_submit_button(
                "🔎 Periksa & Siapkan Penghapusan",
                type="primary",
                use_container_width=True,
            )

        if bulk_submit:
            if not selected_batch_ids:
                st.warning("Belum ada stimulus yang dipilih.")
            else:
                usage_map = get_tka_images_usage_bulk(selected_batch_ids)
                pending_items = []
                for image_id in selected_batch_ids:
                    item = dict(selected_batch_items[image_id])
                    item["known_usages"] = usage_map.get(image_id, [])
                    pending_items.append(item)
                st.session_state[batch_state_key] = pending_items
                st.rerun(scope="fragment")

        batch_pending = st.session_state.get(batch_state_key)
        if batch_pending:
            active_count = 0
            safe_count = 0
            for item in batch_pending:
                usages = item.get("known_usages") or []
                if any(u.get("is_active_window", True) for u in usages):
                    active_count += 1
                else:
                    safe_count += 1

            st.warning(
                f"Konfirmasi: {len(batch_pending)} stimulus dipilih. "
                f"{safe_count} aman diproses, {active_count} masih dipakai TKA aktif."
            )

            with st.expander("Lihat daftar yang akan diproses", expanded=False):
                for item in batch_pending:
                    image_id = item.get("image_id")
                    record = next((r for r in page_images if str(r.get("image_id")) == str(image_id)), {})
                    filename = record.get("filename") or image_id
                    usages = item.get("known_usages") or []
                    active = [u for u in usages if u.get("is_active_window", True)]
                    status = "⛔ TKA masih aktif" if active else "✅ Siap dihapus"
                    st.caption(f"{status} — {filename}")
                    for usage in active:
                        st.caption(
                            f"   ↳ {usage.get('kode_tka', '-')} aktif sampai {usage.get('active_until') or '-'}"
                        )

            c1, c2 = st.columns(2)
            with c1:
                if st.button(
                    "🗑️ Hapus Semua yang Aman",
                    key="tka_bulk_confirm_delete",
                    type="primary",
                    use_container_width=True,
                    disabled=(safe_count == 0),
                ):
                    deleted_ids, blocked = delete_tka_images_safe_bulk(batch_pending)
                    st.session_state.pop(batch_state_key, None)
                    _cached_tka_library.clear()
                    _cached_stimulus_preview.clear()
                    if deleted_ids:
                        st.success(f"{len(deleted_ids)} stimulus berhasil dikeluarkan dari Library aktif.")
                    if blocked:
                        st.warning(f"{len(blocked)} stimulus tidak dihapus karena masih terlindungi.")
                        for item in blocked:
                            st.caption(f"• {item.get('message', 'Tidak dapat dihapus.')}")
                            for usage in item.get("usages") or []:
                                st.caption(
                                    f"  ↳ {usage.get('kode_tka', '-')} aktif sampai {usage.get('active_until') or '-'}"
                                )
                    st.rerun(scope="fragment")

            with c2:
                if st.button(
                    "Batal Pilihan Massal",
                    key="tka_bulk_cancel_delete",
                    use_container_width=True,
                ):
                    st.session_state.pop(batch_state_key, None)
                    st.rerun(scope="fragment")

        # Preview hanya SATU gambar jika memang diperlukan. Dengan default False,
        # klik hapus tidak memaksa Streamlit mengirim ulang puluhan gambar.
        preview_options = {
            str(r.get("image_id")): r
            for r in page_images
            if r.get("image_id")
        }
        preview_ids = list(preview_options.keys())
        if preview_ids:
            preview_choice = st.selectbox(
                "Preview stimulus (opsional)",
                [""] + preview_ids,
                key="tka_manage_preview_id",
                format_func=lambda image_id: (
                    "— Tidak menampilkan preview —"
                    if not image_id
                    else str(preview_options[image_id].get("filename") or image_id)
                ),
            )
            if preview_choice:
                preview_record = preview_options.get(preview_choice, {})
                preview = _cached_stimulus_preview(
                    preview_choice,
                    str(
                        preview_record.get("updated_at")
                        or preview_record.get("created_at")
                        or ""
                    ),
                )
                if preview is not None:
                    st.image(
                        preview,
                        caption=str(preview_record.get("filename") or "Stimulus"),
                        width=360,
                    )

        # Tidak ada st.image() di dalam loop daftar. Ini adalah titik penting untuk
        # performa: satu klik hapus sekarang hanya merender metadata + tombol.
        for record in page_images:
            image_id = str(record.get("image_id") or "")
            filename = str(record.get("filename") or "Stimulus")
            source_type = str(record.get("source_type") or "GURU").upper()
            owner_key = str(record.get("owner_key") or "")

            if not image_id:
                continue

            can_show_delete = (
                source_type == "SYSTEM"
                or (
                    source_type == "GURU"
                    and owner_key.lower() == current_teacher.lower()
                )
            )
            allow_system_delete = source_type == "SYSTEM"

            with st.container(border=True):
                col_info, col_action = st.columns(
                    [7, 1.5],
                    vertical_alignment="center",
                )

                with col_info:
                    st.markdown(f"**{filename}**")
                    st.caption(
                        f"{source_type} • {record.get('jenjang') or '-'} • "
                        f"{record.get('mapel') or '-'}"
                    )
                    topic = (
                        record.get("topic")
                        or infer_tka_topic(
                            filename,
                            record.get("jenjang"),
                            record.get("mapel"),
                        )
                    )
                    st.caption(f"Topik: {topic}")

                with col_action:
                    if can_show_delete:
                        if st.button(
                            "🗑️ Hapus",
                            key=f"delete_tka_image_{image_id}",
                            use_container_width=True,
                        ):
                            # Cek penggunaan hanya saat tombol benar-benar ditekan.
                            # Hasilnya disimpan agar tombol konfirmasi tidak melakukan
                            # query usage kedua kali.
                            usages = get_tka_image_usage(image_id)
                            st.session_state[f"tka_delete_pending_{image_id}"] = {
                                "usages": usages,
                                "allow_system": allow_system_delete,
                                "owner_key": (
                                    None if allow_system_delete else current_teacher
                                ),
                            }

                    elif source_type == "GURU":
                        st.caption("🔒 Bukan milik Anda")

                pending = st.session_state.get(
                    f"tka_delete_pending_{image_id}"
                )

                if pending is not None:
                    usages = pending.get("usages") or []
                    now = _now_wib()
                    active_usages = []
                    expired_usages = []

                    for usage in usages:
                        is_active = bool(usage.get("is_active_window", True))
                        if is_active:
                            active_usages.append(usage)
                        else:
                            expired_usages.append(usage)

                    st.warning(f"⚠️ Konfirmasi penghapusan **{filename}**")

                    if active_usages:
                        st.error(
                            "Stimulus masih digunakan oleh TKA yang masa aktifnya "
                            "belum selesai. Tunggu sampai TKA expired sebelum menghapus."
                        )
                        for usage in active_usages:
                            st.caption(
                                f"• {usage.get('kode_tka', '-')} • "
                                f"{usage.get('mapel', '-')} • aktif sampai "
                                f"{usage.get('active_until') or '-'}"
                            )
                    elif expired_usages:
                        st.info(
                            "TKA yang pernah memakai stimulus ini sudah expired. "
                            "Stimulus dapat dikeluarkan dari Library aktif."
                        )
                    else:
                        st.info("Stimulus belum digunakan oleh paket TKA lain.")

                    confirm_col, cancel_col = st.columns(2)

                    with confirm_col:
                        if st.button(
                            "✅ Ya, Hapus dari Library",
                            key=f"confirm_delete_{image_id}",
                            type="primary",
                            use_container_width=True,
                            disabled=bool(active_usages),
                        ):
                            deleted, delete_message, delete_usages = delete_tka_image_safe(
                                image_id=image_id,
                                owner_key=pending.get("owner_key"),
                                allow_system=bool(pending.get("allow_system")),
                                known_usages=usages,
                            )

                            st.session_state.pop(
                                f"tka_delete_pending_{image_id}",
                                None,
                            )
                            _cached_tka_library.clear()
                            _cached_stimulus_preview.clear()

                            if deleted:
                                st.success(delete_message)
                            else:
                                st.error(delete_message)
                                for usage in delete_usages or []:
                                    st.caption(
                                        f"• {usage.get('kode_tka', '-')} • "
                                        f"aktif sampai {usage.get('active_until') or '-'}"
                                    )

                    with cancel_col:
                        if st.button(
                            "Batal",
                            key=f"cancel_delete_{image_id}",
                            use_container_width=True,
                        ):
                            st.session_state.pop(
                                f"tka_delete_pending_{image_id}",
                                None,
                            )
                            st.info("Penghapusan dibatalkan.")

    else:
        st.info("Library Gambar TKA belum memiliki stimulus.")

