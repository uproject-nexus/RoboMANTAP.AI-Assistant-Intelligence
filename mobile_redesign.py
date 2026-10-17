"""RoboMANTAP bright, mobile-first design system.

This module changes presentation only; it does not modify business or exam logic.
"""

import streamlit as st


def inject_mobile_redesign() -> None:
    """Inject the app-wide warm, high-contrast, mobile-friendly theme."""
    st.markdown(
        r"""
        <style>
        :root {
          --rm-ink: #26324b;
          --rm-muted: #68758d;
          --rm-pink: #f45f88;
          --rm-orange: #ffad5a;
          --rm-mint: #45c6b1;
          --rm-blue: #6d8df7;
          --rm-purple: #a88af3;
          --rm-paper: #fffaf4;
          --rm-line: #f0e7df;
        }
        html, body, [class*="css"] { font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
        .stApp {
          color: var(--rm-ink) !important;
          background:
            radial-gradient(ellipse at 2% 0%, rgba(255, 193, 210, .30), transparent 27%),
            radial-gradient(ellipse at 98% 7%, rgba(255, 218, 165, .32), transparent 28%),
            linear-gradient(180deg, #fffaf4 0%, #fffdf9 44%, #f8fffd 100%) !important;
        }
        [data-testid="stHeader"] { background: rgba(255,250,244,.84) !important; }
        [data-testid="stToolbar"] { right: .75rem; }
        .block-container { max-width: 1120px; padding: 1.2rem 1.15rem 5.5rem !important; }
        [data-testid="stSidebar"] {
          background: linear-gradient(165deg, #fff4e9 0%, #fff8fb 52%, #f1fffb 100%) !important;
          border-right: 1px solid #f1e6df;
        }
        [data-testid="stSidebar"] * { color: var(--rm-ink); }
        h1, h2, h3, h4 { color: var(--rm-ink) !important; letter-spacing: -.025em; }
        p, label, .stMarkdown, [data-testid="stCaptionContainer"] { color: var(--rm-ink); }
        small, [data-testid="stCaptionContainer"] { color: var(--rm-muted) !important; }
        div[data-testid="stButton"] > button,
        div[data-testid="stFormSubmitButton"] > button,
        div[data-testid="stDownloadButton"] > button {
          min-height: 48px !important;
          border-radius: 16px !important;
          border: 1px solid #f0e1d9 !important;
          color: #34415a !important;
          background: linear-gradient(135deg, #ffffff 0%, #fff5ee 100%) !important;
          font-weight: 780 !important;
          box-shadow: 0 5px 14px rgba(75, 64, 83, .06) !important;
          transition: transform .16s ease, box-shadow .16s ease;
          white-space: normal !important;
        }
        div[data-testid="stButton"] > button:hover,
        div[data-testid="stFormSubmitButton"] > button:hover,
        div[data-testid="stDownloadButton"] > button:hover {
          border-color: #f6a5bb !important;
          transform: translateY(-1px);
          box-shadow: 0 8px 18px rgba(244, 95, 136, .12) !important;
        }
        div[data-testid="stButton"] > button[kind="primary"],
        div[data-testid="stFormSubmitButton"] > button[kind="primary"] {
          color: #fff !important;
          border: 0 !important;
          background: linear-gradient(115deg, #f45f88 0%, #ff9569 100%) !important;
          box-shadow: 0 8px 18px rgba(244, 95, 136, .22) !important;
        }
        input, textarea, [data-baseweb="select"] > div, [data-testid="stDateInput"] input {
          background: #fff !important;
          color: var(--rm-ink) !important;
          border-color: #eadfe0 !important;
          border-radius: 13px !important;
        }
        [data-testid="stMetric"], [data-testid="stVerticalBlockBorderWrapper"] {
          border-color: #f0e5de !important;
          border-radius: 19px !important;
        }
        [data-testid="stMetric"] {
          background: rgba(255,255,255,.88) !important;
          padding: 13px 14px !important;
          box-shadow: 0 6px 19px rgba(62, 70, 93, .045);
        }
        [data-testid="stMetricLabel"] { color: var(--rm-muted) !important; }
        [data-testid="stMetricValue"] { color: var(--rm-ink) !important; }
        div[data-testid="stForm"] {
          border: 1px solid #f0e5de !important;
          border-radius: 21px !important;
          background: rgba(255,255,255,.82) !important;
          padding: clamp(14px, 3vw, 22px) !important;
          box-shadow: 0 8px 25px rgba(62,70,93,.04);
        }
        div[role="radiogroup"] { gap: 8px !important; }
        div[role="radiogroup"] label {
          border: 1px solid #efe1e4 !important;
          border-radius: 14px !important;
          background: #fff !important;
          padding: 9px 12px !important;
        }
        div[role="radiogroup"] label:has(input:checked) {
          border-color: #f58eaa !important;
          background: #fff0f4 !important;
        }
        .rm-welcome-hero {
          position: relative; overflow: hidden; padding: clamp(20px, 4vw, 34px);
          margin: 4px 0 20px; border-radius: 27px;
          background: linear-gradient(125deg, #ffe1eb 0%, #fff0cf 48%, #dff9ef 100%) !important;
          border: 1px solid #f4dfe3; box-shadow: 0 14px 34px rgba(90, 69, 91, .07);
        }
        .rm-welcome-top { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:12px; }
        .rm-welcome-top img { height:52px !important; max-width:160px; object-fit:contain; margin:0 !important; }
        .rm-welcome-badge { background:rgba(255,255,255,.78); color:#b94370; padding:7px 10px; border-radius:999px; font-size:10px; font-weight:900; letter-spacing:.04em; }
        .rm-welcome-kicker { color:#bd4a75; font-size:10px; font-weight:900; letter-spacing:.17em; margin-top:10px; }
        .rm-welcome-title { font-size:clamp(31px,5.8vw,50px) !important; line-height:1.02 !important; letter-spacing:-.055em !important; font-weight:950 !important; margin:9px 0 10px !important; }
        .rm-welcome-title span { color:#e45e88; }
        .rm-welcome-copy { max-width:580px; color:#59657b !important; font-size:14px; line-height:1.7; margin-bottom:0; }
        .rm-welcome-tags { display:flex; flex-wrap:wrap; gap:7px; margin-top:15px; }
        .rm-welcome-tags span { background:rgba(255,255,255,.76); border:1px solid rgba(255,255,255,.9); border-radius:999px; padding:8px 11px; color:#45516a; font-weight:800; font-size:11px; }
        .rm-welcome-decoration { position:absolute; right:5%; top:18%; font-size:84px; color:rgba(255,255,255,.55); pointer-events:none; transform:rotate(12deg); }
        .rm-section-heading { margin: 4px 2px 13px; }
        .rm-section-eyebrow { color:#c64d79; font-size:10px; font-weight:900; letter-spacing:.15em; }
        .rm-section-title { color:#29354e; font-size:23px; font-weight:950; letter-spacing:-.04em; margin:4px 0; }
        .rm-section-copy { color:#68758d; font-size:12px; line-height:1.55; }
        .mode-card { min-height:136px; display:flex; flex-direction:column; justify-content:center; padding:20px 16px !important; border-radius:21px !important; box-shadow:0 8px 22px rgba(62,70,93,.05) !important; }
        .mode-card h2 { color:#29354e !important; font-size:20px !important; }
        .mode-card p { color:#59657b !important; font-size:12px !important; }
        .mode-card-mts { background:linear-gradient(135deg,#ffe1eb,#fff5f1) !important; border:1px solid #f5ccd9 !important; }
        .mode-card-ma { background:linear-gradient(135deg,#dff9ef,#edf5ff) !important; border:1px solid #cceee4 !important; }
        .guru-card { background:linear-gradient(130deg,#fff0f5,#fff9ec) !important; color:#29354e !important; border:1px solid #f1dfe4 !important; border-radius:19px !important; }
        .guru-card h2, .guru-card p { color:#29354e !important; }
        .student-hub-card { background:linear-gradient(135deg,#e6e6ff,#ffe5ef) !important; }
        .school-header { background:linear-gradient(120deg,#ffe2ec,#fff0d2,#dcf8ed) !important; border:1px solid #f3dce2 !important; }
        .school-title { color:#29354e !important; }
        .school-subtitle { color:#b84873 !important; }
        .mapel-card { background:#fff !important; border:1px solid #e7e4ef !important; border-radius:18px !important; box-shadow:0 6px 17px rgba(62,70,93,.04); }
        .upn-live-hero { background:linear-gradient(125deg,#e0faf2,#fff1d5,#ffe6ef) !important; border:1px solid #f0dfe3 !important; box-shadow:0 8px 22px rgba(62,70,93,.05) !important; }
        .upn-live-eyebrow { color:#148a78 !important; }
        .upn-live-title, .upn-live-name, .upn-live-score strong { color:#29354e !important; }
        .upn-live-subtitle, .upn-live-sub, .upn-live-foot, .upn-progress-line { color:#68758d !important; }
        .upn-live-count, .upn-live-score { color:#147c6d !important; background:#e4faf2 !important; border-color:#c9efe3 !important; }
        .upn-live-card { background:#fff !important; border:1px solid #eee3e1 !important; border-radius:19px !important; box-shadow:0 7px 20px rgba(62,70,93,.045) !important; }
        .upn-live-chip, .upn-live-foot span { color:#536078 !important; background:#fff8f5 !important; border:1px solid #f0e5de !important; }
        .upn-live-score small { color:#148a78 !important; }
        .upn-progress-line b { color:#128674 !important; }
        .upn-segment { background:#e9e5ed !important; border:1px solid #fff !important; }
        .upn-segment-correct { background:#53c6a6 !important; }
        .upn-segment-wrong { background:#f17b8f !important; }
        .upn-alert-cheat { color:#a92f4b !important; background:#fff0f3 !important; border-color:#f5ccd5 !important; }
        .upn-alert-warn { color:#865a10 !important; background:#fff7df !important; border-color:#f1dfa6 !important; }
        .upn-alert-off { color:#56627a !important; background:#f4f6fa !important; border-color:#e1e6ee !important; }
        .upn-tag-live { color:#187b65 !important; background:#e4faf2 !important; }
        .upn-tag-warn { color:#865a10 !important; background:#fff5d9 !important; }
        .upn-tag-cheat { color:#a92f4b !important; background:#fff0f3 !important; }
        .upn-tag-done { color:#355fba !important; background:#eaf0ff !important; }
        .upn-tag-off { color:#56627a !important; background:#f1f3f8 !important; }
        /* Replace legacy dark hero/card surfaces with the new sunny palette. */
        .premium-hero, .automation-hero {
          color: #26324b !important;
          background: linear-gradient(130deg, #ffe5ed 0%, #fff0cf 48%, #dffaf2 100%) !important;
          border: 1px solid #f7dfe2 !important;
          box-shadow: 0 12px 30px rgba(104, 76, 96, .08) !important;
        }
        .premium-title, .footer-title, .result-card-title, .hub-empty-title { color: #26324b !important; }
        .premium-kicker, .premium-subtitle, .footer-copy, .result-card-copy, .story-meta,
        .hub-code-note, .file-row, .answer-card { color: #526078 !important; }
        .premium-title span { background: linear-gradient(90deg, #d84878, #e98a28); -webkit-background-clip: text; color: transparent; }
        .premium-pills span, .chip {
          color: #3b4860 !important; background: rgba(255,255,255,.72) !important;
          border-color: rgba(225, 170, 184, .55) !important;
        }
        .source-warning { background: #fff8e6 !important; border-color: #f4d99a !important; }
        .source-warning-title { color: #91620f !important; }
        .file-list, .hub-code, .hub-empty, .result-card, .story-card, .premium-footer-card, .answer-card {
          color: #26324b !important; background: #fff !important; border-color: #f0e5de !important;
          box-shadow: 0 6px 18px rgba(62,70,93,.04) !important;
        }
        .hub-code-value { color: #128e80 !important; }
        .story-number { background: linear-gradient(135deg, #f45f88, #ffad5a) !important; }
        [data-testid="stTabs"] button { border-radius: 13px 13px 0 0; }
        [data-testid="stAlert"] { border-radius: 16px !important; }
        hr { border-color: #f0e6df !important; }
        @media (max-width: 760px) {
          .block-container { padding: .8rem .78rem 5.5rem !important; }
          .rm-welcome-hero { padding:20px 16px; border-radius:23px; }
          .rm-welcome-top img { height:44px !important; max-width:122px; }
          .rm-welcome-badge { font-size:9px; padding:6px 8px; }
          .rm-welcome-title { font-size:34px !important; }
          .rm-welcome-decoration { right:3%; top:24%; font-size:54px; }
          .mode-card { min-height:122px; padding:15px 10px !important; }
          h1 { font-size: 1.75rem !important; }
          h2 { font-size: 1.42rem !important; }
          h3 { font-size: 1.17rem !important; }
          [data-testid="stSidebar"] { min-width: min(86vw, 320px); }
          div[role="radiogroup"][aria-orientation="horizontal"], div[role="radiogroup"][style*="flex-direction: row"] { flex-wrap: nowrap !important; overflow-x: auto !important; padding: 3px 1px 9px !important; scrollbar-width: thin; }
          div[role="radiogroup"][aria-orientation="horizontal"] label, div[role="radiogroup"][style*="flex-direction: row"] label { flex: 0 0 auto !important; white-space: nowrap !important; }
          div[data-testid="stButton"] > button, div[data-testid="stFormSubmitButton"] > button,
          div[data-testid="stDownloadButton"] > button { width: 100%; font-size: 14px !important; }
          [data-testid="stMetric"] { padding: 11px !important; }
          .premium-hero { padding: 18px 15px !important; border-radius: 22px !important; }
          .premium-title { font-size: 25px !important; line-height: 1.12 !important; }
          .preview-title { font-size: 19px !important; }
        }
        @media (prefers-reduced-motion: reduce) { * { animation-duration: .01ms !important; transition-duration: .01ms !important; } }
        </style>
        """,
        unsafe_allow_html=True,
    )
