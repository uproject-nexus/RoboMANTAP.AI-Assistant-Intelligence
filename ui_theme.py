"""RoboMANTAP-Intelligence shared UI system: bright, friendly, mobile-first."""
from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st

WIB = ZoneInfo("Asia/Jakarta")

def now_wib() -> datetime:
    return datetime.now(WIB)

def normalize_wib_datetime(value) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("Nilai waktu harus berupa datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=WIB)
    return value.astimezone(WIB)

def format_wib_datetime(value=None, seconds=False) -> str:
    if value is None:
        value = now_wib()
    if not isinstance(value, datetime):
        return str(value)
    value = normalize_wib_datetime(value)
    fmt = "%d %b %Y · %H:%M:%S WIB" if seconds else "%d %b %Y · %H:%M WIB"
    return value.strftime(fmt)

def apply_intelligence_theme() -> None:
    st.markdown(r"""
    <style>
    :root{--rm-bg:#fff9f0;--rm-paper:#fff;--rm-ink:#26324b;--rm-muted:#718096;--rm-blue:#5b6cff;--rm-cyan:#31c5d8;--rm-mint:#43cfa4;--rm-yellow:#ffd66b;--rm-coral:#ff927d;--rm-lilac:#a99aff;--rm-border:#e8eaf3;--rm-shadow:0 12px 32px rgba(75,83,145,.09)}
    html,body,[data-testid="stAppViewContainer"]{background:var(--rm-bg)!important;color:var(--rm-ink)!important;scroll-behavior:smooth}
    [data-testid="stAppViewContainer"]{background-image:radial-gradient(ellipse at 8% 0%,rgba(255,214,107,.16),transparent 28%),radial-gradient(ellipse at 100% 10%,rgba(169,154,255,.12),transparent 25%)!important}
    [data-testid="stHeader"]{background:rgba(255,249,240,.88)!important;backdrop-filter:blur(16px)}
    [data-testid="stAppViewBlockContainer"]{max-width:1480px;padding-top:.65rem;padding-bottom:2.8rem}
    [data-testid="stSidebar"]{background:linear-gradient(180deg,#fff 0%,#f8f8ff 55%,#f1fffb 100%)!important;border-right:1px solid #e8eaf3;box-shadow:5px 0 24px rgba(76,88,155,.035)}
    [data-testid="stSidebar"]>div:first-child{padding-top:.8rem}
    [data-testid="stMarkdownContainer"] p{line-height:1.62;color:var(--rm-ink)}
    [data-testid="stCaptionContainer"]{color:var(--rm-muted)!important}
    h1,h2,h3,h4{color:#26324b!important;letter-spacing:-.035em}
    h1{font-weight:900!important} h2{font-weight:850!important} h3{font-weight:800!important}
    hr{border-color:var(--rm-border)!important}
    div.stButton>button,div.stDownloadButton>button,button[kind="primary"]{border:1px solid rgba(91,108,255,.15)!important;border-radius:14px!important;background:linear-gradient(120deg,#5b6cff 0%,#7c72ff 100%)!important;color:#fff!important;font-weight:800!important;min-height:44px;box-shadow:0 7px 18px rgba(91,108,255,.16);transition:transform .16s ease,box-shadow .16s ease,filter .16s ease}
    div.stButton>button:hover,div.stDownloadButton>button:hover{filter:brightness(1.04);transform:translateY(-1px);box-shadow:0 11px 24px rgba(91,108,255,.22)}
    div.stButton>button:disabled{background:#eef0f8!important;color:#8d94aa!important;box-shadow:none!important;border-color:#e5e8f2!important}
    [data-testid="stTextInput"] input,[data-testid="stNumberInput"] input,[data-testid="stTextArea"] textarea,[data-testid="stSelectbox"] div[data-baseweb="select"],[data-testid="stDateInput"] input,[data-testid="stTimeInput"] input{border-radius:12px!important;background:#fff!important;color:#26324b!important;border-color:#dfe4f0!important}
    [data-testid="stTextInput"] input:focus,[data-testid="stNumberInput"] input:focus,[data-testid="stTextArea"] textarea:focus{border-color:var(--rm-blue)!important;box-shadow:0 0 0 1px var(--rm-blue)!important}
    [data-testid="stForm"]{border:1px solid var(--rm-border);border-radius:20px;padding:1rem;background:rgba(255,255,255,.86);box-shadow:0 8px 24px rgba(75,83,145,.04)}
    [data-testid="stMetric"]{background:linear-gradient(145deg,#fff,#f7f8ff);border:1px solid var(--rm-border);padding:14px 16px;border-radius:18px;box-shadow:0 7px 20px rgba(75,83,145,.045)}
    [data-testid="stMetricLabel"]{color:#718096!important}[data-testid="stMetricValue"]{color:#3848c8!important;font-weight:900}
    [data-testid="stExpander"]{border:1px solid #e4e7f3!important;border-radius:16px!important;overflow:hidden;background:#fff!important}
    [data-testid="stExpander"] summary{background:#fff!important;color:#26324b!important}
    [data-testid="stRadio"]>div{gap:.45rem}[data-testid="stRadio"] div[role="radiogroup"]{flex-wrap:wrap;gap:8px}
    [data-testid="stRadio"] label,[data-testid="stCheckbox"] label{border-radius:11px;color:#34415b}
    [data-testid="stProgress"]>div>div>div>div{background:linear-gradient(90deg,#31c5d8,#43cfa4,#ffd66b)}
    [data-testid="stSpinner"]>div{border-top-color:var(--rm-blue)!important}[data-testid="stSpinner"] p{color:#526078!important;font-weight:700}
    [data-testid="stStatusWidget"]{border:1px solid var(--rm-border);border-radius:999px;background:#fff}
    .rm-topbar{display:flex;align-items:center;gap:12px;padding:11px 15px;margin:2px 0 20px;background:rgba(255,255,255,.84);border:1px solid #eaebf5;border-radius:20px;box-shadow:0 7px 25px rgba(71,80,146,.055)}
    .rm-topbar-mark{display:flex;align-items:center;justify-content:center;width:47px;height:47px;border-radius:15px;background:linear-gradient(145deg,#fff0b9,#d9f8f1)}.rm-topbar-mark img{height:35px!important;max-width:40px;object-fit:contain;margin:0!important}
    .rm-topbar-brand{display:flex;flex-direction:column;line-height:1.2}.rm-topbar-brand b{font-size:17px;font-weight:900;color:#293451}.rm-topbar-brand b span{color:#5b6cff}.rm-topbar-brand small{font-size:10px;color:#8a93aa;margin-top:4px}.rm-topbar-spacer{flex:1}.rm-topbar-date{display:flex;align-items:center;gap:8px;color:#7d879b;font-size:10px;text-align:right;line-height:1.5}.rm-topbar-date b{color:#4654c5;font-size:11px}.rm-live-dot{width:8px;height:8px;border-radius:50%;background:#43cfa4;box-shadow:0 0 0 4px #e1faf1}
    .rm-sidebar-brand{padding:17px 13px 15px;border-radius:22px;background:linear-gradient(145deg,#5b6cff 0%,#8e7bff 53%,#47cfc1 100%);box-shadow:0 12px 25px rgba(91,108,255,.2);color:#fff;text-align:center;margin-bottom:17px}.rm-sidebar-logo{font-size:27px;width:52px;height:52px;display:grid;place-items:center;border-radius:17px;background:rgba(255,255,255,.2);margin:0 auto 8px}.rm-sidebar-name{font-weight:900;font-size:15px;color:#fff;line-height:1.2}.rm-sidebar-name span{display:block;font-size:11px;font-weight:650;color:#eef0ff;margin-top:2px}.rm-sidebar-caption{font-size:10px;color:#f5f4ff;margin-top:8px}.rm-sidebar-status{display:inline-flex;align-items:center;gap:6px;margin-top:10px;padding:5px 8px;border-radius:99px;background:rgba(255,255,255,.17);font-size:9px;color:#fff}.rm-sidebar-status span{width:6px;height:6px;border-radius:50%;background:#aaffd9}
    .rm-sidebar-section{font-size:9px;font-weight:900;letter-spacing:.14em;color:#9aa2ba;margin:17px 4px 7px}.rm-sidebar-link{display:flex;align-items:center;gap:5px;padding:10px 11px;margin:5px 0;border:1px solid #e9ebf6;border-radius:12px;background:#fff;color:#46516c!important;text-decoration:none!important;font-size:12px;font-weight:750}.rm-sidebar-link span{margin-left:auto;color:#8c8dff}.rm-sidebar-tip{margin-top:16px;padding:12px;border-radius:15px;background:linear-gradient(145deg,#fff5d7,#fff);border:1px solid #f5e6ae;color:#6b5a2b;font-size:10px;line-height:1.55}.rm-sidebar-tip strong{color:#8c6b11}.rm-sidebar-footer{text-align:center;border-top:1px dashed #e0e4f0;margin-top:18px;padding:14px 4px 3px;color:#99a1b5;font-size:9px}.rm-sidebar-footer img{display:block;margin:0 auto 6px}.rm-sidebar-footer small{color:#b0b6c7}
    .rm-welcome-hero{position:relative;display:flex;align-items:center;justify-content:space-between;gap:18px;min-height:270px;padding:30px 34px;margin-bottom:25px;border-radius:30px;overflow:hidden;background:linear-gradient(112deg,#fff0b8 0%,#ffe6d9 43%,#e6e2ff 75%,#d9f9f0 100%);border:1px solid rgba(255,255,255,.9);box-shadow:0 18px 45px rgba(97,91,157,.10)}.rm-welcome-copy{position:relative;z-index:2;max-width:690px}.rm-eyebrow{font-size:10px;letter-spacing:.16em;font-weight:900;color:#6455c8;margin-bottom:11px}.rm-sparkle{display:inline-grid;place-items:center;background:#fff;border-radius:8px;width:22px;height:22px;margin-right:5px;color:#ff9d48}.rm-welcome-hero h1{font-size:clamp(29px,3.6vw,45px);line-height:1.12;letter-spacing:-.05em;margin:0;color:#27314a!important}.rm-welcome-hero h1 span{color:#5b60e9}.rm-welcome-hero p{font-size:13px;max-width:620px;color:#626d85;margin:13px 0 0}.rm-hero-chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:17px}.rm-hero-chips span{background:rgba(255,255,255,.72);border:1px solid rgba(255,255,255,.95);border-radius:999px;padding:7px 10px;color:#62607d;font-size:10px;font-weight:750}.rm-hero-art{position:relative;flex:0 0 190px;height:190px;display:grid;place-items:center}.rm-orbit{position:absolute;border-radius:50%;border:2px dashed rgba(91,108,255,.25)}.rm-orbit-one{width:185px;height:185px}.rm-orbit-two{width:138px;height:138px;border-color:rgba(255,146,125,.5)}.rm-book-stack{display:grid;place-items:center;width:98px;height:98px;border-radius:30px;background:linear-gradient(145deg,#fff,#fff8df);box-shadow:0 16px 25px rgba(101,93,156,.15);font-size:48px;transform:rotate(-7deg)}.rm-float-bubble{position:absolute;display:grid;place-items:center;width:39px;height:39px;border-radius:14px;background:#fff;box-shadow:0 7px 18px rgba(71,80,146,.13);font-size:19px}.rm-bubble-one{top:5px;right:22px}.rm-bubble-two{left:0;top:72px}.rm-bubble-three{bottom:0;right:18px}
    /* Playful motion: gentle floating illustrations, slow orbit, and tactile feedback. */
    @keyframes rm-float-soft{0%,100%{transform:translate3d(0,0,0) rotate(-2deg)}50%{transform:translate3d(0,-9px,0) rotate(2deg)}}
    @keyframes rm-float-book{0%,100%{transform:translate3d(0,0,0) rotate(-7deg)}50%{transform:translate3d(0,-8px,0) rotate(-3deg)}}
    @keyframes rm-float-bubble{0%,100%{transform:translate3d(0,0,0) rotate(-3deg)}50%{transform:translate3d(0,-10px,0) rotate(4deg)}}
    @keyframes rm-orbit-drift{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
    @keyframes rm-sparkle-pop{0%,100%{transform:scale(1) rotate(0deg)}45%{transform:scale(1.13) rotate(10deg)}70%{transform:scale(1.04) rotate(-7deg)}}
    @keyframes rm-soft-glow{0%,100%{box-shadow:0 7px 18px rgba(71,80,146,.11)}50%{box-shadow:0 10px 24px rgba(91,108,255,.2)}}
    .rm-orbit-one{animation:rm-orbit-drift 28s linear infinite}
    .rm-orbit-two{animation:rm-orbit-drift 19s linear infinite reverse}
    .rm-book-stack{animation:rm-float-book 4.8s ease-in-out infinite;will-change:transform}
    .rm-bubble-one{animation:rm-float-bubble 4.1s ease-in-out infinite;animation-delay:-.7s}
    .rm-bubble-two{animation:rm-float-bubble 4.8s ease-in-out infinite;animation-delay:-2s}
    .rm-bubble-three{animation:rm-float-bubble 4.4s ease-in-out infinite;animation-delay:-1.3s}
    .rm-sparkle{animation:rm-sparkle-pop 3.2s ease-in-out infinite;transform-origin:center}
    .rm-feature-icon,.rm-portal-icon,.rm-bottom-note>span{animation:rm-float-soft 5.2s ease-in-out infinite;will-change:transform}
    .rm-feature-card:nth-of-type(2n) .rm-feature-icon,.rm-portal-link:nth-of-type(2n) .rm-portal-icon{animation-delay:-1.7s}
    .rm-feature-card:nth-of-type(3n) .rm-feature-icon,.rm-portal-link:nth-of-type(3n) .rm-portal-icon{animation-delay:-3s}
    .rm-sidebar-logo{animation:rm-float-soft 5.6s ease-in-out infinite}
    .rm-live-dot{animation:rm-soft-glow 2.8s ease-in-out infinite}
    .rm-feature-icon:active,.rm-portal-icon:active,.rm-sparkle:active{transform:scale(.9) rotate(-5deg)}
    .rm-sidebar-link:active,.rm-portal-link:active,.rm-whatsapp-button:active{box-shadow:0 3px 9px rgba(71,80,146,.12)}
    button:focus-visible,a:focus-visible,[role="button"]:focus-visible{outline:3px solid rgba(91,108,255,.38)!important;outline-offset:3px!important}
    .rm-section-heading{display:flex;justify-content:space-between;align-items:end;gap:12px;margin:5px 0 15px}.rm-section-heading h2{font-size:23px;line-height:1.2;margin:0!important}.rm-section-heading p{font-size:11px;color:#7b849a;margin:5px 0 0}.rm-eyebrow-color{color:#8280de;margin-bottom:6px}.rm-feature-card{min-height:222px;padding:18px 17px 13px;border:1px solid rgba(255,255,255,.95);border-radius:23px;box-shadow:0 10px 26px rgba(71,80,146,.07);margin-bottom:10px}.rm-card-lilac{background:linear-gradient(145deg,#f0edff,#fff)}.rm-card-mint{background:linear-gradient(145deg,#ddfbef,#fff)}.rm-card-peach{background:linear-gradient(145deg,#ffe6dc,#fff)}.rm-feature-icon{display:grid;place-items:center;width:48px;height:48px;border-radius:16px;background:rgba(255,255,255,.8);box-shadow:0 5px 12px rgba(71,80,146,.06);font-size:25px;margin-bottom:14px}.rm-feature-tag{font-size:8px;font-weight:900;letter-spacing:.13em;color:#8c91a8}.rm-feature-card h3{font-size:19px;margin:6px 0 7px!important}.rm-feature-card p{font-size:11px;line-height:1.6;color:#6c758a;margin:0}.rm-portal-link{display:flex;align-items:center;gap:12px;padding:15px;border-radius:18px;border:1px solid #e7e9f4;background:#fff;color:#2e3953!important;text-decoration:none!important;box-shadow:0 8px 20px rgba(71,80,146,.05);margin:4px 0 12px;transition:transform .15s ease}.rm-portal-link:hover{transform:translateY(-2px)}.rm-portal-icon{display:grid;place-items:center;flex:0 0 44px;height:44px;border-radius:14px;font-size:22px;background:#e8f2ff}.rm-link-yellow .rm-portal-icon{background:#fff2c9}.rm-portal-link span:nth-child(2){display:flex;flex-direction:column;gap:3px}.rm-portal-link b{font-size:13px}.rm-portal-link small{font-size:10px;color:#8992a7}.rm-portal-link strong{margin-left:auto;color:#7775ed}.rm-registration-intro{padding:5px 2px 10px}.rm-registration-intro p{font-size:11px;color:#7b849a;margin:4px 0}.rm-whatsapp-button{display:block;text-align:center;padding:13px;border-radius:13px;background:linear-gradient(100deg,#25d366,#56dca0);color:#073b2c!important;text-decoration:none!important;font-size:13px;font-weight:900;margin-top:8px;box-shadow:0 8px 20px rgba(37,211,102,.15)}.rm-bottom-note{display:flex;gap:12px;align-items:center;margin-top:20px;padding:16px 18px;border-radius:18px;background:linear-gradient(100deg,#f1edff,#e7fbf5);border:1px solid #fff}.rm-bottom-note>span{font-size:25px}.rm-bottom-note div{display:flex;flex-direction:column;gap:3px}.rm-bottom-note b{font-size:12px;color:#514f94}.rm-bottom-note small{font-size:10px;color:#81889d}
    /* Normalize old feature cards so non-landing screens also adopt the new design. */
    .mode-card,.guru-card,.premium-hero,.automation-hero,.preview-hero,.result-card,.story-card,.premium-footer-card,.answer-card,.file-list,.hub-code,.hub-empty{background:#fff!important;color:#26324b!important;border:1px solid #e7e9f3!important;border-radius:18px!important;box-shadow:0 8px 24px rgba(71,80,146,.055)!important}.mode-card h2,.mode-card p,.premium-title,.premium-subtitle,.preview-title,.result-card-title,.footer-title,.hub-empty-title,.answer-card{color:#26324b!important}.mode-card{padding:18px!important}.mode-card h2{font-size:17px!important}.mode-card p{font-size:11px!important;color:#758099!important}.premium-kicker,.hub-code-label,.preview-label,.footer-kicker{color:#7775d8!important}.premium-pills span,.chip,.answer-card,.file-row,.hub-code-note,.footer-copy,.result-card-copy,.story-meta{color:#5f6a83!important;background:#f7f8ff!important}.hub-code-value{color:#4f61de!important}.story-number{background:linear-gradient(135deg,#5b6cff,#45cdb6)!important}.source-warning{background:#fff6dc!important;border-color:#f2df9e!important}.source-warning-title{color:#9a7512!important}.source-warning code{color:#4056b9!important;background:#e9edff!important}.upn-live-card,.upn-live-hero,.upn-live-score,.upn-live-chip,.upn-live-foot span{background:#fff!important;color:#34415b!important;border-color:#e6e9f4!important}.upn-live-name,.upn-live-score strong,.upn-live-score small,.upn-live-sub,.upn-live-meta,.upn-live-foot,.upn-progress-line,.upn-progress-line b{color:#34415b!important}.upn-segment{background:#e8eaf4!important}.upn-segment-correct{background:#43cfa4!important}.upn-segment-wrong{background:#ff927d!important}.upn-segment-current{box-shadow:0 0 0 2px #e7e8ff!important}
    @media(max-width:800px){[data-testid="stAppViewBlockContainer"]{padding:.5rem .65rem 1.8rem}.rm-topbar{padding:9px 10px;border-radius:16px;margin-bottom:14px}.rm-topbar-mark{width:39px;height:39px}.rm-topbar-mark img{height:29px!important}.rm-topbar-brand b{font-size:14px}.rm-topbar-brand small{font-size:9px}.rm-topbar-date{font-size:8px}.rm-welcome-hero{padding:21px 18px;border-radius:23px;min-height:0}.rm-hero-art{flex-basis:100px;height:115px;transform:scale(.72);transform-origin:center right;margin-left:-18px}.rm-orbit-one{width:145px;height:145px}.rm-orbit-two{width:110px;height:110px}.rm-book-stack{width:75px;height:75px;font-size:37px;border-radius:23px}.rm-welcome-hero h1{font-size:29px}.rm-welcome-hero p{font-size:11px}.rm-hero-chips span{font-size:9px;padding:6px 8px}.rm-section-heading h2{font-size:20px}.rm-feature-card{min-height:0;padding:15px}.rm-feature-card h3{font-size:17px}.rm-feature-card p{font-size:11px}div.stButton>button,div.stDownloadButton>button{min-height:43px;font-size:13px!important}.rm-sidebar-name{font-size:14px}}
    @media(max-width:520px){.rm-welcome-hero{display:block}.rm-hero-art{position:absolute;right:0;bottom:-4px;opacity:.43;transform:scale(.78);transform-origin:bottom right}.rm-welcome-copy{max-width:100%}.rm-welcome-hero p{max-width:95%}.rm-hero-chips{max-width:90%}.rm-topbar-date{gap:4px}.rm-topbar-brand b{font-size:12px}.rm-topbar-brand small{font-size:8px}.rm-topbar-mark{width:34px;height:34px}.rm-topbar-mark img{height:25px!important}.rm-topbar{gap:8px}}
    /* Interactive polish: hover for pointer devices, tap feedback for touch screens. */
    @media (hover:hover) and (pointer:fine){
      div.stButton>button:not(:disabled),div.stDownloadButton>button:not(:disabled),[data-testid="stFormSubmitButton"] button:not(:disabled){will-change:transform}
      div.stButton>button:not(:disabled):hover,div.stDownloadButton>button:not(:disabled):hover,[data-testid="stFormSubmitButton"] button:not(:disabled):hover{transform:translateY(-2px);filter:saturate(1.08) brightness(1.025);box-shadow:0 13px 26px rgba(91,108,255,.22)!important}
      .rm-feature-card,.rm-bottom-note,.rm-topbar,.rm-sidebar-brand,.rm-portal-link,[data-testid="stMetric"],[data-testid="stExpander"],[data-testid="stForm"],[data-testid="stAlert"],[data-testid="stDataFrame"],[data-testid="stTable"]{transition:transform .18s ease,box-shadow .18s ease,border-color .18s ease}
      .rm-feature-card:hover,.rm-portal-link:hover,[data-testid="stMetric"]:hover{transform:translateY(-3px);box-shadow:0 15px 30px rgba(71,80,146,.12)!important;border-color:#d8dcff!important}
      .rm-sidebar-link:hover{background:#f2f3ff!important;border-color:#d9dcff!important;transform:translateX(2px)}
      [data-testid="stExpander"]:hover,[data-testid="stForm"]:hover{border-color:#d9dcff!important;box-shadow:0 12px 28px rgba(71,80,146,.08)}
    }
    .rm-sidebar-link,.rm-portal-link,.rm-whatsapp-button{transition:transform .16s ease,box-shadow .16s ease,background-color .16s ease,filter .16s ease}
    .rm-sidebar-link:active,.rm-portal-link:active,.rm-whatsapp-button:active,div.stButton>button:active,div.stDownloadButton>button:active{transform:scale(.985);filter:brightness(.98)}
    [data-testid="stAppViewBlockContainer"],[data-testid="stMainBlockContainer"]{min-width:0!important;width:100%;box-sizing:border-box}
    [data-testid="stMarkdownContainer"],[data-testid="stVerticalBlock"],[data-testid="stHorizontalBlock"],[data-testid="column"]{min-width:0}
    [data-testid="stImage"] img,[data-testid="stMarkdownContainer"] img{max-width:100%!important;height:auto}
    [data-testid="stDataFrame"],[data-testid="stTable"],[data-testid="stCode"]{max-width:100%;overflow-x:auto}
    [data-testid="stDataFrame"]>div{max-width:100%}
    [data-testid="stTabs"] [role="tablist"]{max-width:100%;overflow-x:auto;flex-wrap:nowrap;scrollbar-width:thin}
    [data-testid="stTabs"] button[role="tab"]{white-space:nowrap;flex-shrink:0}
    input,textarea,select,button{scroll-margin-bottom:24px}
    @media(max-width:800px){
      [data-testid="stAppViewBlockContainer"],[data-testid="stMainBlockContainer"]{padding-left:clamp(10px,2.5vw,18px)!important;padding-right:clamp(10px,2.5vw,18px)!important;padding-top:.55rem!important;max-width:100vw!important;overflow-x:clip}
      [data-testid="stSidebar"]{max-width:min(88vw,340px)!important}
      [data-testid="stSidebarContent"]{padding-left:12px!important;padding-right:12px!important}
      .rm-welcome-hero{width:100%;box-sizing:border-box;overflow:hidden}
      .rm-feature-card{box-sizing:border-box;width:100%;overflow-wrap:anywhere}
      .rm-topbar{width:100%;box-sizing:border-box;min-width:0}
      .rm-topbar-brand{min-width:0;overflow-wrap:anywhere}
      .rm-topbar-date{flex-shrink:0}
      .rm-section-heading{align-items:flex-start;flex-wrap:wrap}
      [data-testid="stForm"]{padding:.8rem!important;border-radius:16px!important}
      [data-testid="stMetric"]{padding:11px!important;min-width:0;overflow-wrap:anywhere}
      [data-testid="stMetricValue"]{font-size:clamp(1.15rem,5vw,1.8rem)!important;overflow-wrap:anywhere}
      [data-testid="stMarkdownContainer"] table{display:block;max-width:100%;overflow-x:auto;white-space:nowrap}
      [data-testid="stRadio"] div[role="radiogroup"]{gap:6px!important}
      [data-testid="stRadio"] label{padding:5px 8px!important}
      .rm-sidebar-link{min-height:42px;padding:11px 12px;font-size:13px}
      .rm-whatsapp-button{min-height:46px;display:flex;align-items:center;justify-content:center}
    }
    @media(max-width:640px){
      /* Stack Streamlit columns on phones so narrow widgets never collide. */
      [data-testid="stHorizontalBlock"]{display:flex!important;flex-wrap:wrap!important;gap:.65rem!important;align-items:stretch!important}
      [data-testid="stHorizontalBlock"]>[data-testid="column"]{flex:1 1 100%!important;width:100%!important;min-width:0!important;max-width:100%!important}
      [data-testid="stHorizontalBlock"]>[data-testid="column"]>div{min-width:0!important;max-width:100%!important}
      [data-testid="stAppViewBlockContainer"]{padding-left:10px!important;padding-right:10px!important}
      .rm-topbar{gap:7px;padding:8px;border-radius:15px}
      .rm-topbar-mark{width:34px;height:34px;flex:0 0 34px;border-radius:11px}
      .rm-topbar-mark img{height:24px!important;max-width:28px}
      .rm-topbar-brand{flex:1 1 auto;min-width:0}
      .rm-topbar-brand b{font-size:clamp(11px,3.2vw,13px);overflow-wrap:anywhere}
      .rm-topbar-brand small{font-size:8px;white-space:normal}
      .rm-topbar-date{font-size:8px;gap:4px;max-width:36%;line-height:1.35}
      .rm-topbar-date b{font-size:9px}
      .rm-live-dot{width:6px;height:6px;flex:0 0 6px}
      .rm-welcome-hero{display:flex;flex-direction:column;align-items:stretch;gap:8px;padding:19px 15px 14px;border-radius:21px;margin-bottom:17px}
      .rm-welcome-copy{max-width:100%;width:100%;min-width:0}
      .rm-welcome-hero h1{font-size:clamp(25px,7.2vw,32px);max-width:100%;overflow-wrap:anywhere}
      .rm-welcome-hero p{font-size:12px;line-height:1.55;max-width:100%}
      /* On phones, move the playful art into its own centered row instead of pinning it to the right edge. */
      .rm-hero-art{position:relative;right:auto;bottom:auto;align-self:center;flex:0 0 154px;width:180px;max-width:100%;height:154px;margin:7px auto 0;transform:none;transform-origin:center;opacity:1;pointer-events:none;overflow:visible}
      .rm-orbit-one{width:148px;height:148px}.rm-orbit-two{width:112px;height:112px}
      .rm-book-stack{width:76px;height:76px;font-size:38px;border-radius:23px}
      .rm-bubble-one{top:2px;right:16px}.rm-bubble-two{left:2px;top:59px}.rm-bubble-three{bottom:0;right:14px}
      .rm-hero-chips{max-width:100%;gap:5px}
      .rm-hero-chips span{font-size:9px;padding:5px 7px}
      .rm-section-heading h2{font-size:19px}
      .rm-feature-card{padding:15px;border-radius:19px;margin-bottom:0}
      .rm-feature-card h3{font-size:17px}
      .rm-feature-card p{font-size:12px}
      div.stButton>button,div.stDownloadButton>button,[data-testid="stFormSubmitButton"] button{width:100%;min-height:46px!important;font-size:14px!important;border-radius:13px!important;white-space:normal!important}
      [data-testid="stTextInput"] input,[data-testid="stNumberInput"] input,[data-testid="stDateInput"] input,[data-testid="stTimeInput"] input{min-height:44px!important;font-size:16px!important}
      [data-testid="stTextArea"] textarea{font-size:16px!important}
      [data-testid="stSelectbox"] div[data-baseweb="select"]{min-height:44px!important}
      [data-testid="stExpander"] summary{padding-top:.75rem!important;padding-bottom:.75rem!important}
      [data-testid="stAlert"]{padding:.8rem!important;overflow-wrap:anywhere}
      [data-testid="stProgress"]{margin-top:.35rem;margin-bottom:.35rem}
      .rm-portal-link{padding:12px;gap:9px;border-radius:15px}
      .rm-portal-icon{flex-basis:38px;height:38px;font-size:19px}
      .rm-portal-link b{font-size:12px}.rm-portal-link small{font-size:10px;overflow-wrap:anywhere}
      .rm-bottom-note{align-items:flex-start;padding:13px;border-radius:15px}
      .rm-bottom-note small{line-height:1.5}
    }
    @media(max-width:360px){
      .rm-topbar-date{font-size:7px;max-width:34%}.rm-topbar-date b{font-size:8px}
      .rm-topbar-brand b{font-size:10px}.rm-topbar-brand small{font-size:7px}
      .rm-welcome-hero{padding:16px 12px}.rm-welcome-hero h1{font-size:24px}
      .rm-hero-art{flex-basis:136px;width:154px;height:136px;margin-top:5px;opacity:1}
      .rm-orbit-one{width:132px;height:132px}.rm-orbit-two{width:98px;height:98px}
      .rm-book-stack{width:67px;height:67px;font-size:33px;border-radius:20px}
      .rm-bubble-one{right:7px}.rm-bubble-three{right:6px}
      .rm-hero-chips span{font-size:8px}
      [data-testid="stMetric"]{padding:9px!important}
    }
    @media(hover:none),(pointer:coarse){
      div.stButton>button,div.stDownloadButton>button,[data-testid="stFormSubmitButton"] button{transition:transform .12s ease,filter .12s ease,box-shadow .12s ease;-webkit-tap-highlight-color:transparent}
      div.stButton>button:active,div.stDownloadButton>button:active,[data-testid="stFormSubmitButton"] button:active{transform:scale(.98);filter:brightness(.97)}
      .rm-feature-card:hover,.rm-portal-link:hover,[data-testid="stMetric"]:hover{transform:none}
      .rm-feature-icon:active,.rm-portal-icon:active,.rm-bottom-note>span:active{animation-play-state:paused;transform:scale(.92)}
    }
    @media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;transition:none!important;animation:none!important;transform:none!important}}
    </style>
    """, unsafe_allow_html=True)
