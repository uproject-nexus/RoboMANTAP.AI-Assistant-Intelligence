"""Game Seru - game edukasi sederhana untuk santriwati (Matematika, Sains, Islam, Hijaiyah)."""
import random
import streamlit as st

ROUNDS = 10

def _math_questions(n=ROUNDS):
    out = []
    for _ in range(n):
        op = random.choice(["+", "-", "×"])
        if op == "×":
            a, b = random.randint(2, 12), random.randint(2, 12); ans = a * b
        elif op == "+":
            a, b = random.randint(10, 99), random.randint(10, 99); ans = a + b
        else:
            a, b = random.randint(30, 99), random.randint(10, 29); ans = a - b
        opts = {ans}
        while len(opts) < 4:
            opts.add(max(0, ans + random.choice([-10, -2, -1, 1, 2, 10, 5])))
        opts = [str(x) for x in random.sample(sorted(opts), 4)]
        out.append((f"{a} {op} {b} = ?", opts, opts.index(str(ans)), f"Jawaban: {ans}"))
    return out

SAINS = [
    ("Planet terdekat dari Matahari?", ["Merkurius", "Venus", "Mars", "Bumi"], 0, "Merkurius paling dekat dengan Matahari."),
    ("Gas yang dihirup manusia untuk bernapas?", ["Nitrogen", "Oksigen", "Helium", "Karbon dioksida"], 1, "Tubuh memakai oksigen."),
    ("Air membeku pada suhu...", ["0°C", "50°C", "100°C", "-50°C"], 0, "Titik beku air 0°C."),
    ("Bagian tumbuhan yang membuat makanan?", ["Akar", "Batang", "Daun", "Bunga"], 2, "Fotosintesis terjadi di daun."),
    ("Jumlah kaki laba-laba?", ["6", "8", "10", "4"], 1, "Laba-laba punya 8 kaki."),
    ("Organ pemompa darah?", ["Paru-paru", "Hati", "Jantung", "Ginjal"], 2, "Jantung memompa darah."),
    ("Benda yang menarik besi?", ["Magnet", "Kayu", "Kaca", "Karet"], 0, "Magnet menarik logam tertentu."),
    ("Perubahan air menjadi uap disebut...", ["Mencair", "Menguap", "Membeku", "Mengembun"], 1, "Menguap = cair menjadi gas."),
    ("Hewan yang berkembang biak dengan bertelur?", ["Kucing", "Sapi", "Ayam", "Kelinci"], 2, "Ayam bertelur (ovipar)."),
    ("Satelit alami Bumi?", ["Bulan", "Mars", "Venus", "Bintang"], 0, "Bulan mengorbit Bumi."),
    ("Alat untuk mengukur suhu?", ["Penggaris", "Termometer", "Timbangan", "Jam"], 1, "Termometer mengukur suhu."),
    ("Sumber energi utama di Bumi?", ["Bulan", "Angin", "Matahari", "Petir"], 2, "Matahari sumber energi utama."),
]
ISLAM = [
    ("Jumlah rukun Islam?", ["3", "5", "6", "7"], 1, "Rukun Islam ada 5."),
    ("Jumlah rukun iman?", ["5", "6", "7", "4"], 1, "Rukun iman ada 6."),
    ("Kitab suci umat Islam?", ["Injil", "Taurat", "Al-Qur'an", "Zabur"], 2, "Al-Qur'an diturunkan kepada Nabi Muhammad ﷺ."),
    ("Jumlah shalat wajib sehari semalam?", ["3", "4", "5", "6"], 2, "Subuh, Zuhur, Asar, Magrib, Isya."),
    ("Bulan puasa Ramadan adalah bulan ke...", ["8", "9", "10", "12"], 1, "Ramadan bulan ke-9 Hijriah."),
    ("Malaikat pembawa wahyu?", ["Mikail", "Israfil", "Jibril", "Izrail"], 2, "Malaikat Jibril."),
    ("Kota tempat Ka'bah berada?", ["Madinah", "Makkah", "Kairo", "Jakarta"], 1, "Ka'bah di Makkah."),
    ("Surat pertama dalam Al-Qur'an?", ["Al-Baqarah", "Al-Ikhlas", "Al-Fatihah", "An-Nas"], 2, "Al-Fatihah."),
    ("Nabi terakhir adalah...", ["Nabi Isa", "Nabi Musa", "Nabi Muhammad ﷺ", "Nabi Ibrahim"], 2, "Penutup para nabi."),
    ("Ucapan saat memulai sesuatu yang baik?", ["Bismillah", "Astaghfirullah", "Innalillah", "Subhanallah"], 0, "Bismillah."),
    ("Kewajiban memberi sebagian harta kepada yang berhak?", ["Zakat", "Haji", "Syahadat", "Shalat"], 0, "Zakat."),
    ("Hari raya setelah Ramadan?", ["Idul Adha", "Idul Fitri", "Maulid", "Isra Miraj"], 1, "Idul Fitri."),
]
HIJAIYAH = [("ا","Alif"),("ب","Ba"),("ت","Ta"),("ث","Tsa"),("ج","Jim"),("ح","Ha"),("خ","Kho"),("د","Dal"),
            ("ذ","Dzal"),("ر","Ra"),("ز","Zai"),("س","Sin"),("ش","Syin"),("ص","Shad"),("ض","Dhad"),("ط","Tha"),
            ("ظ","Zha"),("ع","'Ain"),("غ","Ghain"),("ف","Fa"),("ق","Qaf"),("ك","Kaf"),("ل","Lam"),("م","Mim"),
            ("ن","Nun"),("و","Wawu"),("ه","Ha"),("ي","Ya")]

def _hijaiyah_questions(n=ROUNDS):
    out = []
    for ch, nm in random.sample(HIJAIYAH, n):
        wrong = random.sample([x[1] for x in HIJAIYAH if x[1] != nm], 3)
        opts = random.sample(wrong + [nm], 4)
        out.append((f'<div class="hv-ar">{ch}</div>Apa nama huruf ini?', opts, opts.index(nm), f"Huruf ini bernama {nm}."))
    return out

GAMES = {
    "math":  ("🧮 Kilat Matematika", "Hitung cepat tambah, kurang, kali!", "linear-gradient(135deg,#ffd23f,#ff9f6b)", _math_questions),
    "sains": ("🔬 Detektif Sains", "Jelajahi alam, tubuh, dan planet.", "linear-gradient(135deg,#4cc9f0,#06d6a0)", lambda: random.sample(SAINS, ROUNDS)),
    "islam": ("🕌 Cerdas Islami", "Seputar rukun, nabi, dan ibadah.", "linear-gradient(135deg,#a58bff,#ff7ac6)", lambda: random.sample(ISLAM, ROUNDS)),
    "hijaiyah": ("📖 Tebak Hijaiyah", "Kenali huruf hijaiyah dengan seru.", "linear-gradient(135deg,#ff7ac6,#ffd23f)", _hijaiyah_questions),
}

def _start(key):
    st.session_state.gh = {"game": key, "qs": GAMES[key][3](), "i": 0, "score": 0, "picked": None}

def _pick(idx):
    g = st.session_state.gh
    if g["picked"] is None:
        g["picked"] = idx
        if idx == g["qs"][g["i"]][2]:
            g["score"] += 1

def _next():
    g = st.session_state.gh
    g["i"] += 1; g["picked"] = None

def _exit():
    st.session_state.gh = None

def render_games_hub(name: str = "Santri") -> None:
    st.markdown('<div class="sm-section-kicker">Belajar sambil bermain</div><div class="sm-section-title">Game Seru 🎮</div>', unsafe_allow_html=True)
    g = st.session_state.get("gh")
    best = st.session_state.setdefault("gh_best", {})

    if not g:
        st.caption(f"Halo {name.split()[0] if name else 'Santri'}! Pilih game, jawab 10 soal, kumpulkan bintang ⭐")
        for key, (title, desc, bg, _) in GAMES.items():
            st.markdown(f'<div class="hv-game" style="background:{bg}">{title}<small>{desc}</small></div>', unsafe_allow_html=True)
            b = best.get(key)
            st.button(f"Main sekarang{'  · Terbaik: ' + str(b) + '/10' if b is not None else ''}", key=f"play_{key}",
                      use_container_width=True, type="primary", on_click=_start, args=(key,))
        return

    title = GAMES[g["game"]][0]
    total = len(g["qs"])
    if g["i"] >= total:
        sc = g["score"]
        best[g["game"]] = max(sc, best.get(g["game"], 0))
        stars = "⭐" * (3 if sc >= 9 else 2 if sc >= 6 else 1 if sc >= 3 else 0) or "💪"
        if sc >= 9: st.balloons()
        st.markdown(f'<div class="hv-q">Selesai! {stars}<br>Skor: {sc}/{total}<br><small>Masya Allah, terus semangat!</small></div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        c1.button("🔁 Main lagi", use_container_width=True, type="primary", on_click=_start, args=(g["game"],))
        c2.button("🏠 Menu game", use_container_width=True, on_click=_exit)
        return

    q, opts, ans, why = g["qs"][g["i"]]
    st.markdown(f'<span class="hv-chip">{title}</span><span class="hv-chip">Soal {g["i"]+1}/{total}</span><span class="hv-chip">⭐ {g["score"]}</span>', unsafe_allow_html=True)
    st.progress(g["i"] / total)
    st.markdown(f'<div class="hv-q">{q}</div>', unsafe_allow_html=True)
    for i, o in enumerate(opts):
        label = o
        if g["picked"] is not None:
            label = ("✅ " if i == ans else "❌ " if i == g["picked"] else "") + o
        st.button(label, key=f"opt_{g['i']}_{i}", use_container_width=True,
                  disabled=g["picked"] is not None, on_click=_pick, args=(i,))
    if g["picked"] is not None:
        (st.success if g["picked"] == ans else st.warning)(("Benar! 🎉 " if g["picked"] == ans else "Belum tepat. ") + why)
        st.button("Lanjut ➜" if g["i"] + 1 < total else "Lihat hasil 🏆", key=f"next_{g['i']}",
                  type="primary", use_container_width=True, on_click=_next)
    st.button("Keluar", key="quit_game", on_click=_exit)
