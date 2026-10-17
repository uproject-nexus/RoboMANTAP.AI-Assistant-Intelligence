"""Tema 'Happy Vibes' - mobile-first, penuh warna. Tidak mengubah logika aplikasi."""
import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@600;700;800;900&display=swap');
:root{--hv-pink:#ff5fa2;--hv-purple:#7c4dff;--hv-blue:#29b6f6;--hv-mint:#1de9b6;--hv-sun:#ffc93c;--hv-ink:#2b2350;--hv-bg:#fff8fd}
html,body,.stApp,button,input,textarea{font-family:'Nunito',system-ui,sans-serif!important}
.stApp{background:linear-gradient(160deg,#fff0f8 0%,#f1ecff 45%,#e6f9ff 100%)!important;color:var(--hv-ink)}
.block-container{max-width:760px!important;padding:.8rem .8rem 5rem!important}
header[data-testid="stHeader"]{background:transparent}
.sm-hero{background:linear-gradient(135deg,var(--hv-pink),var(--hv-purple) 55%,var(--hv-blue))!important;border-radius:28px!important;box-shadow:0 14px 34px rgba(124,77,255,.30)!important}
.sm-card,div[data-testid="stVerticalBlockBorderWrapper"]{background:#fff!important;border:2px solid #f3e6ff!important;border-radius:22px!important;box-shadow:0 6px 18px rgba(124,77,255,.10)!important}
.sm-section-kicker{color:var(--hv-pink)!important}
.sm-section-title{color:var(--hv-ink)!important}
/* tombol besar, mudah disentuh */
.stButton>button,.stDownloadButton>button{min-height:52px;border-radius:18px;font-weight:800;border:2px solid #e3d4ff;background:#fff;color:var(--hv-ink);transition:transform .1s}
.stButton>button:active{transform:scale(.97)}
.stButton>button[kind="primary"]{background:linear-gradient(135deg,var(--hv-pink),var(--hv-purple));color:#fff;border:0;box-shadow:0 8px 18px rgba(255,95,162,.35)}
/* navigasi: chip yang bisa digeser di HP */
div[role="radiogroup"]{flex-wrap:nowrap!important;overflow-x:auto;gap:8px!important;padding:6px 2px 10px;scrollbar-width:none}
div[role="radiogroup"]::-webkit-scrollbar{display:none}
div[role="radiogroup"]>label{flex:0 0 auto;background:#fff;border:2px solid #e3d4ff;border-radius:999px;padding:8px 14px!important;font-weight:800;white-space:nowrap;cursor:pointer}
div[role="radiogroup"]>label:has(input:checked){background:linear-gradient(135deg,var(--hv-sun),var(--hv-pink));border-color:transparent;color:#fff}
div[role="radiogroup"]>label>div:first-child{display:none}
@media(max-width:640px){
 [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;gap:.5rem!important}
 [data-testid="stHorizontalBlock"]>[data-testid="column"]{min-width:100%!important}
 h1{font-size:1.6rem!important}h2,h3{font-size:1.2rem!important}
}
.hv-game{border-radius:24px;padding:18px;color:#fff;margin:8px 0;font-weight:800;box-shadow:0 8px 20px rgba(0,0,0,.12)}
.hv-game small{display:block;opacity:.9;font-weight:700;margin-top:4px}
.hv-q{background:#fff;border:3px dashed var(--hv-purple);border-radius:24px;padding:20px;font-size:1.35rem;font-weight:900;text-align:center;margin:10px 0}
.hv-ar{font-size:3.2rem;line-height:1.3}
.hv-chip{display:inline-block;background:#fff;border:2px solid #e3d4ff;border-radius:999px;padding:4px 12px;font-weight:800;margin-right:6px}
</style>
"""

def inject_theme():
    st.markdown(CSS, unsafe_allow_html=True)
