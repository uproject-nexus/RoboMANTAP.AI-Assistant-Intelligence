"""Santri Ceria - tema cerah mobile-first (tanpa mode gelap) + kutipan motivasi harian."""
import streamlit as st
from datetime import date

QUOTES = [
 ("Sesungguhnya bersama kesulitan ada kemudahan.", "QS. Al-Insyirah: 6"),
 ("Barang siapa menempuh jalan menuntut ilmu, Allah mudahkan jalannya ke surga.", "HR. Muslim"),
 ("Sebaik-baik manusia adalah yang paling bermanfaat bagi orang lain.", "HR. Ahmad"),
 ("Mulai dari yang kecil, tapi mulailah hari ini.", "Semangat Santriwati"),
 ("Tidak ada kata terlambat untuk jadi lebih baik dari kemarin.", "Semangat Santriwati"),
 ("Bersabarlah, hasil terbaik datang pada waktu terbaik.", "Semangat Santriwati"),
 ("Dan katakanlah: Ya Tuhanku, tambahkanlah ilmu kepadaku.", "QS. Thaha: 114"),
 ("Satu halaman hari ini lebih baik daripada seribu rencana besok.", "Semangat Santriwati"),
 ("Allah tidak membebani seseorang melainkan sesuai kesanggupannya.", "QS. Al-Baqarah: 286"),
 ("Salah itu wajar. Yang penting kamu mau mencoba lagi.", "Semangat Santriwati"),
 ("Ilmu itu cahaya, dan cahaya tidak diberikan kepada yang malas.", "Nasihat Ulama"),
 ("Kamu hebat karena mau belajar, bukan karena selalu benar.", "Semangat Santriwati"),
]

def daily_quote():
    return QUOTES[date.today().toordinal() % len(QUOTES)]

def greeting(hour: int) -> str:
    return "Selamat pagi" if hour < 11 else "Selamat siang" if hour < 15 else "Selamat sore" if hour < 18 else "Selamat malam"

CSS = r"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Baloo+2:wght@600;700;800&family=Nunito:wght@600;700;800;900&display=swap');
:root{color-scheme:light only;--c-sky:#4cc9f0;--c-violet:#7b5cff;--c-pink:#ff7ac6;--c-sun:#ffd23f;--c-mint:#06d6a0;--c-coral:#ff6b6b;--c-ink:#1f2a52;--c-mute:#5d6b8a;--c-line:#e6ebff}
html,body,.stApp,[data-testid="stAppViewContainer"]{background:#f6fbff!important;color:var(--c-ink)!important;color-scheme:light only}
.stApp{background:radial-gradient(circle at 0 0,#fff3c4 0,transparent 32%),radial-gradient(circle at 100% 0,#e3d9ff 0,transparent 34%),radial-gradient(circle at 50% 100%,#d4f7ff 0,transparent 40%),#f6fbff!important}
html,body,button,input,textarea,select{font-family:'Nunito',system-ui,sans-serif!important}
h1,h2,h3,h4{font-family:'Baloo 2','Nunito',sans-serif!important;color:var(--c-ink)!important;letter-spacing:-.01em}
p,li,label,span,[data-testid="stMarkdownContainer"]{color:inherit}
[data-testid="stHeader"]{background:rgba(246,251,255,.85)!important;backdrop-filter:blur(12px)}
[data-testid="stSidebar"]{background:#fff!important;border-right:2px solid var(--c-line)}
.block-container,[data-testid="stAppViewBlockContainer"]{max-width:820px!important;padding:.8rem .85rem 5rem!important}
/* tombol: besar & ramah sentuh */
.stButton>button,.stDownloadButton>button,.stFormSubmitButton>button{min-height:52px;border-radius:18px;border:2px solid var(--c-line);background:#fff;color:var(--c-ink);font-weight:800;box-shadow:0 4px 0 var(--c-line);transition:.12s}
.stButton>button:active{transform:translateY(3px);box-shadow:none}
.stButton>button[kind="primary"],.stFormSubmitButton>button{background:linear-gradient(135deg,var(--c-violet),var(--c-sky));color:#fff!important;border:0;box-shadow:0 5px 0 #5a43c9}
input,textarea,[data-baseweb="select"]>div{background:#fff!important;color:var(--c-ink)!important;border-radius:16px!important;border:2px solid var(--c-line)!important}
[data-testid="stMetric"],[data-testid="stForm"],[data-testid="stExpander"],div[data-testid="stVerticalBlockBorderWrapper"]{background:#fff!important;border:2px solid var(--c-line)!important;border-radius:22px!important;box-shadow:0 6px 18px rgba(76,90,160,.08)}
[data-testid="stProgress"]>div>div>div>div{background:linear-gradient(90deg,var(--c-sky),var(--c-mint),var(--c-sun))}
/* menu: chip geser, aktif berwarna */
div[role="radiogroup"]{flex-wrap:nowrap!important;overflow-x:auto;gap:8px!important;padding:8px 2px 12px;scrollbar-width:none;position:sticky;top:3rem;z-index:5}
div[role="radiogroup"]::-webkit-scrollbar{display:none}
div[role="radiogroup"]>label{flex:0 0 auto;background:#fff;border:2px solid var(--c-line);border-radius:999px;padding:9px 16px!important;font-weight:800;white-space:nowrap}
div[role="radiogroup"]>label:has(input:checked){background:linear-gradient(135deg,var(--c-sun),var(--c-coral));border-color:transparent;box-shadow:0 5px 14px rgba(255,107,107,.35)}
div[role="radiogroup"]>label>div:first-child{display:none}
/* hero + kutipan */
.sm-hero{position:relative;overflow:hidden;border-radius:30px!important;padding:22px 20px!important;background:linear-gradient(135deg,var(--c-violet),var(--c-sky))!important;color:#fff!important;box-shadow:0 14px 32px rgba(123,92,255,.28)!important}
.sm-hero *{color:#fff!important}
.sm-hero:after{content:"☪️";position:absolute;right:14px;top:6px;font-size:64px;opacity:.22}
.sm-title{font-family:'Baloo 2',sans-serif;font-size:clamp(26px,7vw,40px)!important;font-weight:800;line-height:1.1}
.sm-chip{display:inline-block;background:rgba(255,255,255,.22);border-radius:999px;padding:5px 12px;font-size:12px;font-weight:800;margin:4px 6px 0 0}
.hv-quote{background:#fff;border:2px dashed var(--c-sun);border-radius:24px;padding:16px 18px;margin:12px 0;box-shadow:0 6px 0 #fff0b3}
.hv-quote b{display:block;font-size:1.02rem;line-height:1.5}.hv-quote small{color:var(--c-mute);font-weight:800}
/* kartu, jadwal, bagian lama */
.sm-card,.portal-agenda-card{background:#fff!important;border:2px solid var(--c-line)!important;border-radius:22px!important;color:var(--c-ink)!important;box-shadow:0 6px 18px rgba(76,90,160,.08)!important}
.sm-section-kicker,.pi-kicker2{color:var(--c-pink)!important;font-weight:900;letter-spacing:.1em;text-transform:uppercase;font-size:11px}
.sm-section-title,.pi-h2{color:var(--c-ink)!important;font-family:'Baloo 2',sans-serif;font-size:1.5rem;font-weight:800}
.portal-agenda-card{display:flex;align-items:center;gap:12px;padding:12px;margin:10px 0}
.portal-agenda-date{min-width:62px;text-align:center;border-radius:18px;padding:8px 6px;background:linear-gradient(135deg,var(--c-sun),var(--c-coral));color:#fff!important}
.portal-agenda-date span{display:block;font-size:26px;font-weight:900;line-height:1}.portal-agenda-date small{font-weight:800;text-transform:uppercase}
.portal-agenda-body{flex:1;min-width:0}.portal-agenda-body strong{font-size:1rem}
.portal-agenda-status{background:var(--c-mint);color:#04332a;border-radius:999px;padding:5px 10px;font-size:11px;font-weight:900;white-space:nowrap}
.premium-hero{background:linear-gradient(135deg,var(--c-violet),var(--c-pink))!important;color:#fff!important}
.premium-title,.premium-title span,.premium-kicker,.premium-subtitle{color:#fff!important;-webkit-text-fill-color:#fff!important;background:none!important}
.file-list,.hub-code,.hub-empty,.result-card,.story-card,.premium-footer-card,.answer-card,.source-warning{background:#fff!important;color:var(--c-ink)!important;border:2px solid var(--c-line)!important}
/* game */
.hv-game{border-radius:24px;padding:18px 20px;color:#1f2a52;margin:10px 0 6px;font-size:1.1rem;font-weight:900}
.hv-game small{display:block;font-weight:700;margin-top:4px}
.hv-q{background:#fff;border:3px dashed var(--c-violet);border-radius:24px;padding:20px;font-size:1.3rem;font-weight:900;text-align:center;margin:10px 0}
.hv-ar{font-size:3.2rem;line-height:1.3}
.hv-chip{display:inline-block;background:#fff;border:2px solid var(--c-line);border-radius:999px;padding:4px 12px;font-weight:800;margin:0 6px 6px 0}
@media(max-width:640px){
 [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;gap:.6rem!important}
 [data-testid="stHorizontalBlock"]>[data-testid="stColumn"],[data-testid="stHorizontalBlock"]>[data-testid="column"]{min-width:100%!important;flex:1 1 100%!important}
 input,textarea{font-size:16px!important}
}
</style>
"""

def apply_happy_theme():
    st.markdown(CSS, unsafe_allow_html=True)

def render_quote():
    q, src = daily_quote()
    st.markdown(f'<div class="hv-quote"><small>💌 Semangat hari ini</small><b>“{q}”</b><small>— {src}</small></div>', unsafe_allow_html=True)
