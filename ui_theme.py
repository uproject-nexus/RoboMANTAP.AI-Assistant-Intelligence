"""Shared visual system and Jakarta-time helpers for RoboMANTAP-Intelligence."""
from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st

WIB = ZoneInfo("Asia/Jakarta")

def now_wib() -> datetime:
    """Return an aware datetime in the application's operational timezone."""
    return datetime.now(WIB)

def normalize_wib_datetime(value) -> datetime:
    """Normalize legacy naive and timezone-aware datetimes to aware WIB."""
    if not isinstance(value, datetime):
        raise TypeError("Nilai waktu harus berupa datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=WIB)
    return value.astimezone(WIB)

def format_wib_datetime(value=None, seconds=False) -> str:
    """Format a timestamp for humans; naive values are interpreted as WIB."""
    if value is None:
        value = now_wib()
    if not isinstance(value, datetime):
        return str(value)
    value = normalize_wib_datetime(value)
    fmt = "%d %b %Y · %H:%M:%S WIB" if seconds else "%d %b %Y · %H:%M WIB"
    return value.strftime(fmt)

def apply_intelligence_theme() -> None:
    """Apply the shared premium UI layer after legacy styles to normalize all screens."""
    st.markdown(r"""
    <style>
    :root {
      --rm-bg: #0b1220;
      --rm-panel: #111c2e;
      --rm-panel-soft: #152238;
      --rm-border: rgba(148,163,184,.17);
      --rm-mint: #6ee7c2;
      --rm-green: #10b981;
      --rm-text: #edf5fb;
      --rm-muted: #9fb0c5;
    }
    html, body, [data-testid="stAppViewContainer"] { scroll-behavior: smooth; }
    [data-testid="stAppViewContainer"] {
      background:
        radial-gradient(ellipse at 10% -10%, rgba(16,185,129,.10), transparent 35%),
        radial-gradient(ellipse at 100% 0%, rgba(99,102,241,.09), transparent 30%),
        var(--rm-bg);
      color: var(--rm-text);
    }
    [data-testid="stHeader"] { background: rgba(11,18,32,.78); backdrop-filter: blur(14px); }
    [data-testid="stAppViewBlockContainer"] { max-width: 1600px; padding-top: 1.15rem; padding-bottom: 3rem; }
    [data-testid="stSidebar"] { background: linear-gradient(180deg,#0f1b2c 0%,#0b1220 100%); border-right: 1px solid var(--rm-border); }
    [data-testid="stSidebar"] > div:first-child { padding-top: 1rem; }
    [data-testid="stMarkdownContainer"] p { line-height: 1.58; }
    [data-testid="stCaptionContainer"] { color: var(--rm-muted); }
    h1,h2,h3 { letter-spacing: -.025em; }
    h1 { font-weight: 850 !important; }
    h2,h3 { font-weight: 760 !important; }
    hr { border-color: var(--rm-border); }
    div.stButton > button, div.stDownloadButton > button, button[kind="primary"] {
      border: 1px solid rgba(110,231,194,.42) !important;
      border-radius: 13px !important;
      background: linear-gradient(135deg,#10b981 0%,#0d9488 56%,#0f766e 100%) !important;
      color: #041b1a !important;
      font-weight: 780 !important;
      min-height: 43px;
      box-shadow: 0 7px 22px rgba(16,185,129,.12);
      transition: transform .16s ease, box-shadow .16s ease, filter .16s ease;
    }
    div.stButton > button:hover, div.stDownloadButton > button:hover {
      filter: brightness(1.06); transform: translateY(-1px);
      box-shadow: 0 10px 26px rgba(16,185,129,.20);
    }
    div.stButton > button:active { transform: translateY(0); }
    [data-testid="stTextInput"] input, [data-testid="stNumberInput"] input,
    [data-testid="stTextArea"] textarea, [data-testid="stSelectbox"] div[data-baseweb="select"],
    [data-testid="stDateInput"] input, [data-testid="stTimeInput"] input {
      border-radius: 11px !important;
    }
    [data-testid="stTextInput"] input:focus, [data-testid="stNumberInput"] input:focus,
    [data-testid="stTextArea"] textarea:focus { border-color: var(--rm-green) !important; box-shadow: 0 0 0 1px var(--rm-green) !important; }
    [data-testid="stForm"] { border: 1px solid var(--rm-border); border-radius: 16px; padding: 1rem; background: rgba(17,28,46,.48); }
    [data-testid="stMetric"] { background: linear-gradient(145deg,rgba(21,34,56,.88),rgba(17,28,46,.68)); border: 1px solid var(--rm-border); padding: 14px 16px; border-radius: 16px; }
    [data-testid="stExpander"] { border: 1px solid var(--rm-border); border-radius: 14px; overflow: hidden; background: rgba(17,28,46,.34); }
    [data-testid="stRadio"] > div { gap: .4rem; }
    [data-testid="stRadio"] div[role="radiogroup"] { flex-wrap: wrap; gap: 8px; }
    [data-testid="stRadio"] label, [data-testid="stCheckbox"] label { border-radius: 10px; }
    [data-testid="stProgress"] > div > div > div > div { background: linear-gradient(90deg,#10b981,#6ee7c2); }
    [data-testid="stSpinner"] > div { border-top-color: #6ee7c2 !important; }
    [data-testid="stSpinner"] p { color: #c8d7e8; font-weight: 650; }
    [data-testid="stStatusWidget"] { border: 1px solid var(--rm-border); border-radius: 999px; background: rgba(17,28,46,.9); }
    [data-testid="stProgress"] { margin: .35rem 0; }
    .rm-brand-hero {
      display: flex; align-items: center; gap: 20px; padding: 22px 26px; margin: 2px 0 22px;
      border: 1px solid rgba(110,231,194,.20); border-radius: 24px; overflow: hidden;
      background: radial-gradient(circle at 88% 0%,rgba(99,102,241,.19),transparent 32%),
                  radial-gradient(circle at 8% 110%,rgba(16,185,129,.17),transparent 34%),
                  linear-gradient(135deg,#101d30 0%,#0e1829 55%,#102b2a 100%);
      box-shadow: 0 18px 48px rgba(0,0,0,.18);
    }
    .rm-brand-logo { flex: 0 0 auto; display:flex; align-items:center; justify-content:center; width:94px; height:94px; border-radius:22px; background:rgba(255,255,255,.045); border:1px solid rgba(255,255,255,.08); }
    .rm-brand-logo img { height:68px !important; max-width:80px; object-fit:contain; margin:0 !important; }
    .rm-brand-copy { min-width:0; }
    .rm-brand-eyebrow { color:#6ee7c2; font-size:10px; letter-spacing:.18em; font-weight:850; margin-bottom:5px; }
    .rm-brand-title { font-size:clamp(23px,3vw,35px); font-weight:900; letter-spacing:-.045em; line-height:1.1; color:#f7fbff; }
    .rm-brand-title span { color:#6ee7c2; }
    .rm-brand-subtitle { color:#bdcbdc; font-size:13px; margin-top:7px; }
    .rm-brand-meta { display:flex; flex-wrap:wrap; gap:8px 14px; margin-top:12px; color:#a7bacf; font-size:10px; }
    .rm-brand-meta span { display:inline-flex; align-items:center; gap:5px; }
    .stAlert { border-radius: 13px; }
    @media(max-width:720px) {
      [data-testid="stAppViewBlockContainer"] { padding: .7rem .75rem 2rem; }
      .rm-brand-hero { align-items:flex-start; gap:12px; padding:16px; border-radius:19px; }
      .rm-brand-logo { width:58px; height:58px; border-radius:15px; }
      .rm-brand-logo img { height:43px !important; max-width:47px; }
      .rm-brand-eyebrow { font-size:8px; letter-spacing:.11em; }
      .rm-brand-title { font-size:23px; overflow-wrap:anywhere; }
      .rm-brand-subtitle { font-size:11px; }
      .rm-brand-meta { font-size:9px; gap:5px 10px; }
      [data-testid="stMetric"] { padding:10px; }
      [data-testid="stForm"] { padding:.75rem; }
      div.stButton > button, div.stDownloadButton > button { min-height:42px; font-size:14px !important; }
    }
    @media(prefers-reduced-motion: reduce) {
      *,*::before,*::after { scroll-behavior:auto !important; transition:none !important; animation:none !important; }
    }
    </style>
    """, unsafe_allow_html=True)
