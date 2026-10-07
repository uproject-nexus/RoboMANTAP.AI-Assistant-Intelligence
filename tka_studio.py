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
    backfill_tka_image_metadata,
    can_delete_tka_image,
    delete_tka_image_safe,
    ensure_tka_tables,
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


@st.cache_data(ttl=600, show_spinner=False)
def _cached_all_tka_library(limit=2000):
    """Load Library metadata once; subsequent filter changes run in memory."""
    return list_tka_images(limit=limit)


def _filter_tka_library(
    records,
    source_type=None,
    owner_key=None,
    jenjang=None,
    mapel=None,
    search=None,
):
    source_type = str(source_type or "").upper() or None
    owner_key = str(owner_key or "").strip().casefold()
    wanted_jenjang = str(jenjang or "").strip().casefold()
    wanted_mapel = str(mapel or "").strip().casefold()
    search_value = str(search or "").strip().casefold()

    filtered = []
    for record in records or []:
        record_source = str(record.get("source_type") or "").upper()
        record_owner = str(record.get("owner_key") or "").strip().casefold()
        if source_type and record_source != source_type:
            continue
        if owner_key and not (
            record_source == "SYSTEM" or record_owner == owner_key
        ):
            continue
        if wanted_jenjang and str(record.get("jenjang") or "").strip().casefold() != wanted_jenjang:
            continue
        if wanted_mapel and str(record.get("mapel") or "").strip().casefold() != wanted_mapel:
            continue
        if search_value:
            tags = record.get("tags") or []
            if not isinstance(tags, list):
                tags = [tags]
            haystack = " ".join(
                [
                    str(record.get("filename") or ""),
                    str(record.get("topic") or ""),
                    str(record.get("description") or ""),
                    " ".join(str(x) for x in tags),
                ]
            ).casefold()
            if search_value not in haystack:
                continue
        filtered.append(record)
    return filtered


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_tka_image_record(image_id):
    return get_tka_image(str(image_id))


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_tka_thumbnail(image_id, max_size=360):
    record = get_tka_image(str(image_id))
    if not record:
        return None
    image = _image_for_streamlit(record.get("image_data"))
    if image is None:
        return None
    try:
        image = image.copy()
        image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        has_alpha = image.mode in {"RGBA", "LA"} or (
            image.mode == "P" and "transparency" in image.info
        )
        if has_alpha:
            image.save(output, format="PNG", optimize=True)
        else:
            if image.mode != "RGB":
                image = image.convert("RGB")
            image.save(output, format="JPEG", quality=82, optimize=True)
        return output.getvalue()
    except Exception:
        return None


def _clear_tka_image_caches():
    try:
        _cached_all_tka_library.clear()
        _cached_tka_image_record.clear()
        _cached_tka_thumbnail.clear()
    except Exception:
        pass


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

    if not st.session_state.get("_tka_tables_ready"):
        ensure_tka_tables()
        st.session_state["_tka_tables_ready"] = True

    if not st.session_state.get("_tka_metadata_backfilled"):
        backfill_tka_image_metadata(limit=1000)
        st.session_state["_tka_metadata_backfilled"] = True

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

                _clear_tka_image_caches()

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

        library = _filter_tka_library(
            _cached_all_tka_library(),
            source_type=source_type,
            owner_key=owner_key,
            jenjang=jenjang,
            mapel=mapel,
            search=search_term,
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

                    record = _cached_tka_image_record(
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
    # TKA IMAGE LIBRARY / STIMULUS MANAGEMENT
    # =========================================================
    st.markdown("---")
    st.markdown("### 🗂️ Library Gambar TKA")
    st.caption(
        "Kelola Stimulus mengikuti filter Jenjang + Mata Uji aktif. "
        "Metadata di-cache dan preview memakai thumbnail agar filter tidak "
        "mengunduh serta memproses ulang seluruh BYTEA gambar."
    )

    manage_source_type = None
    manage_owner_key = None
    manage_search = None
    manage_source_label = "Semua Sumber"

    if source_mode == "Pilih dari Library TKA":
        manage_search = search_term
        manage_owner_key = owner
        manage_source_label = source_filter
        if source_filter == "Gambar Sistem":
            manage_source_type = "SYSTEM"
            manage_owner_key = None
        elif source_filter == "Gambar Saya":
            manage_source_type = "GURU"

    manage_limit = 24
    manage_page_key = "tka_manage_page"
    current_page = max(1, int(st.session_state.get(manage_page_key, 1)))

    management_images = _filter_tka_library(
        _cached_all_tka_library(),
        source_type=manage_source_type,
        owner_key=manage_owner_key,
        jenjang=jenjang,
        mapel=mapel,
        search=manage_search,
    )

    total_manage = len(management_images)
    total_pages = max(1, (total_manage + manage_limit - 1) // manage_limit)
    if current_page > total_pages:
        current_page = total_pages
        st.session_state[manage_page_key] = current_page

    st.caption(
        f"Filter aktif: **{jenjang} • {mapel} • {manage_source_label}**"
        + (f" • pencarian: **{manage_search.strip()}**" if manage_search and manage_search.strip() else "")
        + f" • {total_manage} stimulus"
    )

    if not management_images:
        st.info("Tidak ada stimulus yang cocok dengan filter aktif.")
    else:
        page_start = (current_page - 1) * manage_limit
        page_items = management_images[page_start:page_start + manage_limit]

        nav_left, nav_info, nav_right = st.columns([1, 3, 1])
        with nav_left:
            if st.button("← Sebelumnya", disabled=current_page <= 1,
                         key="tka_manage_prev", use_container_width=True):
                st.session_state[manage_page_key] = current_page - 1
                st.rerun(scope="fragment")
        with nav_info:
            st.markdown(
                f"<div style='text-align:center;padding:7px 0;font-size:12px;'>"
                f"Halaman <b>{current_page}</b> / <b>{total_pages}</b></div>",
                unsafe_allow_html=True,
            )
        with nav_right:
            if st.button("Berikutnya →", disabled=current_page >= total_pages,
                         key="tka_manage_next", use_container_width=True):
                st.session_state[manage_page_key] = current_page + 1
                st.rerun(scope="fragment")

        current_teacher = teacher_name.strip() or "GuruMANTAP"
        # Current project has one authenticated GuruMANTAP portal role.
        # No separate Admin table/identity exists in this ZIP, so the existing
        # authenticated portal permission is used for SYSTEM management.
        system_delete_authorized = bool(st.session_state.get("guru_auth", False))

        for record in page_items:
            image_id = str(record.get("image_id") or "")
            if not image_id:
                continue

            filename = str(record.get("filename") or "Stimulus")
            source_type = str(record.get("source_type") or "GURU").upper()
            owner_key = str(record.get("owner_key") or "")
            topic = (
                str(record.get("topic") or "").strip()
                or infer_tka_topic(filename, record.get("jenjang"), record.get("mapel"))
            )
            description = str(record.get("description") or "").strip()

            guru_delete_allowed = (
                source_type == "GURU"
                and owner_key.lower() == current_teacher.lower()
            )
            system_delete_allowed = (
                source_type == "SYSTEM" and system_delete_authorized
            )
            can_show_delete = guru_delete_allowed or system_delete_allowed

            with st.container(border=True):
                col_img, col_info, col_action = st.columns(
                    [1.35, 4.3, 1.35], vertical_alignment="center"
                )

                with col_img:
                    thumb = _cached_tka_thumbnail(image_id, 360)
                    if thumb:
                        st.image(thumb, caption=filename, use_container_width=True)

                with col_info:
                    st.markdown(f"**{filename}**")
                    st.caption(
                        f"{source_type} • {record.get('jenjang') or '-'} • "
                        f"{record.get('mapel') or '-'}"
                    )
                    st.caption(f"**Topik:** {topic}")
                    if description and description != topic:
                        st.caption(f"Deskripsi: {description}")
                    if source_type == "SYSTEM":
                        st.caption(
                            "🛡️ System Image Library UPN"
                            + (
                                " • dapat dikelola oleh portal terotorisasi."
                                if system_delete_authorized
                                else " • hanya dapat digunakan."
                            )
                        )
                    else:
                        st.caption(f"👤 Pemilik: {owner_key or '-'}")

                with col_action:
                    if can_show_delete:
                        if st.button("🗑️ Hapus", key=f"delete_tka_image_{image_id}",
                                     use_container_width=True):
                            allowed, message, usages = can_delete_tka_image(
                                image_id=image_id,
                                owner_key=current_teacher if source_type == "GURU" else None,
                                allow_system=(
                                    source_type == "SYSTEM" and system_delete_authorized
                                ),
                            )
                            if not allowed:
                                st.session_state[f"tka_delete_warning_{image_id}"] = {
                                    "message": message, "usages": usages
                                }
                            else:
                                st.session_state[f"tka_delete_confirm_{image_id}"] = True
                            st.rerun(scope="fragment")
                    elif source_type == "GURU":
                        st.caption("🔒 Bukan milik Anda")
                    else:
                        st.caption("🔒 Admin UPN diperlukan")

                if st.session_state.get(f"tka_delete_confirm_{image_id}", False):
                    st.warning(f"⚠️ Hapus **{filename}** dari Library TKA?")
                    confirm_col, cancel_col = st.columns(2)
                    with confirm_col:
                        if st.button("✅ Ya, Hapus", key=f"confirm_delete_{image_id}",
                                     type="primary", use_container_width=True):
                            deleted, delete_message, usages = delete_tka_image_safe(
                                image_id=image_id,
                                owner_key=current_teacher if source_type == "GURU" else None,
                                allow_system=(
                                    source_type == "SYSTEM" and system_delete_authorized
                                ),
                            )
                            st.session_state.pop(f"tka_delete_confirm_{image_id}", None)
                            if deleted:
                                st.session_state["tka_library_selection"] = [
                                    str(x) for x in st.session_state.get(
                                        "tka_library_selection", []
                                    ) if str(x) != image_id
                                ]
                                st.session_state["tka_selected_image_ids"] = [
                                    str(x) for x in st.session_state.get(
                                        "tka_selected_image_ids", []
                                    ) if str(x) != image_id
                                ]
                                _clear_tka_image_caches()
                                st.success(delete_message)
                                st.rerun(scope="fragment")
                            else:
                                st.session_state[f"tka_delete_warning_{image_id}"] = {
                                    "message": delete_message, "usages": usages
                                }
                                st.rerun(scope="fragment")
                    with cancel_col:
                        if st.button("Batal", key=f"cancel_delete_{image_id}",
                                     use_container_width=True):
                            st.session_state.pop(f"tka_delete_confirm_{image_id}", None)
                            st.rerun(scope="fragment")

                warning_payload = st.session_state.get(
                    f"tka_delete_warning_{image_id}"
                )
                if warning_payload:
                    st.error(
                        "🚫 " + warning_payload.get(
                            "message", "Gambar tidak dapat dihapus."
                        )
                    )
                    usages = warning_payload.get("usages") or []
                    if usages:
                        st.markdown("**Gambar ini masih digunakan oleh paket TKA:**")
                        for usage in usages:
                            st.markdown(
                                f"- **{usage.get('kode_tka', '-')}** • "
                                f"{usage.get('jenjang', '-')} • {usage.get('mapel', '-')}"
                            )
                    if st.button("Tutup", key=f"close_delete_warning_{image_id}"):
                        st.session_state.pop(f"tka_delete_warning_{image_id}", None)
                        st.rerun(scope="fragment")

    st.caption(
        "ℹ️ Hapus menggunakan soft-delete. Stimulus yang sudah digunakan paket "
        "TKA published tetap dilindungi dan tidak dapat dihapus."
    )

