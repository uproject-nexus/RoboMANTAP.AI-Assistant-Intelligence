import streamlit as st
from datetime import datetime, timedelta

def inject_tka_css():
    st.markdown("""
    <style>
        /* Paksa 3 kolom tombol bawah tetap sejajar di HP */
        .bottom-nav-container [data-testid="column"] {
            min-width: 30% !important;
            padding: 0px 4px !important;
        }
        
        /* Tombol Navigasi Bawah Pusmendik */
        .btn-merah > button { background-color: #dc3545 !important; color: white !important; border-radius: 30px !important; border: none !important; }
        .btn-kuning > button { background-color: #ffc107 !important; color: black !important; border-radius: 30px !important; border: none !important; font-weight: bold !important; }
        .btn-biru > button { background-color: #007bff !important; color: white !important; border-radius: 30px !important; border: none !important; }
        
        /* Warna Tombol Daftar Soal (Grid) */
        .grid-putih > button { background-color: white !important; color: black !important; border: 1px solid #ccc !important; }
        .grid-biru > button { background-color: #007bff !important; color: white !important; border: 1px solid #007bff !important; }
        .grid-kuning > button { background-color: #ffc107 !important; color: black !important; border: 1px solid #ffc107 !important; font-weight: bold !important; }
        
        .kategori-box {
            background-color: var(--secondary-background-color); 
            padding: 12px; 
            border-radius: 8px; 
            border: 1px solid rgba(128,128,128,0.2);
            margin-bottom: 10px;
        }
    </style>
    """, unsafe_allow_html=True)

def render_tka_quiz(update_db_function):
    inject_tka_css()
    
    # Inisialisasi State Khusus TKA
    if "tka_idx" not in st.session_state: st.session_state.tka_idx = 0
    if "tka_answers" not in st.session_state: st.session_state.tka_answers = {}
    if "tka_ragu" not in st.session_state: st.session_state.tka_ragu = set()
    
    quiz_data = st.session_state.tka_quiz_data
    total_soal = len(quiz_data)
    curr_idx = st.session_state.tka_idx
    q = quiz_data[curr_idx]
    
    # ==========================================
    # 1. TOP BAR (INFO, TIMER, DAFTAR SOAL)
    # ==========================================
    c_info, c_timer, c_daftar = st.columns([2, 1.5, 1.5])
    with c_info:
        st.markdown(f"**Soal nomor {curr_idx + 1}**")
        st.caption(f"{st.session_state.tka_mapel} - {st.session_state.tka_jenjang}")
        
    with c_timer:
        # Menghitung sisa waktu (Misal TKA selalu 60 Menit)
        if "tka_start_time" not in st.session_state:
            st.session_state.tka_start_time = datetime.utcnow() + timedelta(hours=7)
            
        terpakai = int(((datetime.utcnow() + timedelta(hours=7)) - st.session_state.tka_start_time).total_seconds())
        sisa = max(0, 3600 - terpakai) # 60 menit
        st.markdown(f"⏱️ **{sisa // 60:02d}:{sisa % 60:02d}**")
        
        if sisa <= 0:
            st.session_state.page = "tka_result"
            st.rerun()

    with c_daftar:
        with st.popover("Daftar Soal ▦"):
            st.markdown("### Daftar Soal")
            cols = st.columns(5)
            for i in range(total_soal):
                col_idx = i % 5
                
                # Logika Warna Pusmendik
                if i in st.session_state.tka_ragu:
                    css_class = "grid-kuning"
                    icon = "🟨"
                elif i in st.session_state.tka_answers and st.session_state.tka_answers[i]:
                    css_class = "grid-biru"
                    icon = "✅"
                else:
                    css_class = "grid-putih"
                    icon = "⬜"

                with cols[col_idx]:
                    st.markdown(f'<div class="{css_class}">', unsafe_allow_html=True)
                    if st.button(f"{i+1}", key=f"nav_tka_{i}", use_container_width=True):
                        st.session_state.tka_idx = i
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)

    st.divider()

    # ==========================================
    # 2. KONTEN SOAL MULTI-TIPE
    # ==========================================
    st.markdown(q["question"])
    st.write("")
    
    q_type = q.get("type", "pg_biasa")
    trigger_sync = False

    # TIPE A: Pilihan Ganda Biasa
    if q_type == "pg_biasa":
        opts = q["options"]
        saved = st.session_state.tka_answers.get(curr_idx, None)
        def_idx = opts.index(saved) if saved in opts else None
        
        ans = st.radio("Pilih jawaban:", opts, index=def_idx, key=f"tka_r_{curr_idx}", label_visibility="collapsed")
        if ans and ans != saved:
            st.session_state.tka_answers[curr_idx] = ans
            trigger_sync = True

    # TIPE B: Pilihan Ganda Kompleks (Banyak Jawaban)
    elif q_type == "pg_kompleks":
        opts = q["options"]
        saved_list = st.session_state.tka_answers.get(curr_idx, [])
        new_list = []
        
        st.markdown("**Pilih semua pernyataan yang benar:**")
        for opt in opts:
            if st.checkbox(opt, value=(opt in saved_list), key=f"tka_cb_{curr_idx}_{opt}"):
                new_list.append(opt)
                
        if set(new_list) != set(saved_list):
            st.session_state.tka_answers[curr_idx] = new_list
            trigger_sync = True

    # TIPE C: Kategori (Benar/Salah Mobile Friendly)
    elif q_type == "kategori":
        stmts = q.get("statements", [])
        labels = q.get("options_label", ["Benar", "Salah"])
        saved_dict = st.session_state.tka_answers.get(curr_idx, {})
        new_dict = saved_dict.copy()
        
        st.markdown('<div class="kategori-box">', unsafe_allow_html=True)
        for i, stmt in enumerate(stmts):
            st.markdown(f"**{i+1}.** {stmt}")
            saved_val = saved_dict.get(str(i))
            idx_val = labels.index(saved_val) if saved_val in labels else None
            
            ans = st.radio("Pilih:", labels, index=idx_val, key=f"tka_kat_{curr_idx}_{i}", horizontal=True, label_visibility="collapsed")
            if ans: new_dict[str(i)] = ans
            st.markdown("<hr style='margin: 8px 0; opacity: 0.1;'>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        if new_dict != saved_dict:
            st.session_state.tka_answers[curr_idx] = new_dict
            trigger_sync = True

    # Sinkronisasi ke DB Guru (Live Monitoring)
    if trigger_sync:
        detail = []
        for i in range(total_soal):
            u_ans = st.session_state.tka_answers.get(i, None)
            tipe = quiz_data[i].get("type", "pg_biasa")
            if not u_ans:
                detail.append(None)
            else:
                if tipe == "pg_biasa": detail.append(u_ans == quiz_data[i]["correct_answer"])
                elif tipe == "pg_kompleks": detail.append(set(u_ans) == set(quiz_data[i]["correct_answer"]))
                elif tipe == "kategori": detail.append(u_ans == quiz_data[i]["correct_answer"])

        update_db_function(
            st.session_state.session_id, st.session_state.tka_nama_siswa,
            st.session_state.tka_jenjang, f"{st.session_state.tka_mapel} (TKA)",
            curr_idx + 1, detail, "BERJALAN", is_custom=False
        )

    st.write("")
    st.write("")

    # ==========================================
    # 3. BOTTOM NAV (SEBELUMNYA | RAGU | BERIKUTNYA)
    # ==========================================
    st.markdown('<div class="bottom-nav-container">', unsafe_allow_html=True)
    b1, b2, b3 = st.columns(3)
    
    with b1:
        st.markdown('<div class="btn-merah">', unsafe_allow_html=True)
        if st.button("⬅️ Sblm", use_container_width=True) and curr_idx > 0:
            st.session_state.tka_idx -= 1
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    with b2:
        st.markdown('<div class="btn-kuning">', unsafe_allow_html=True)
        is_ragu = curr_idx in st.session_state.tka_ragu
        lbl_ragu = "☑️ Ragu" if is_ragu else "🟨 Ragu"
        if st.button(lbl_ragu, use_container_width=True):
            if is_ragu: st.session_state.tka_ragu.remove(curr_idx)
            else: st.session_state.tka_ragu.add(curr_idx)
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    with b3:
        st.markdown('<div class="btn-biru">', unsafe_allow_html=True)
        if curr_idx < total_soal - 1:
            if st.button("Berikutnya ➡️", use_container_width=True):
                st.session_state.tka_idx += 1
                st.rerun()
        else:
            if st.button("Selesai 🏁", use_container_width=True):
                st.session_state.page = "tka_result"
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
