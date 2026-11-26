"""Estilo cálido compartido por las páginas de feria (distinto del dashboard)."""

BG, CARD, LINE = '#f6eee3', '#fffaf3', '#e6d6c2'
INK, MUTED, FAINT = '#3a2618', '#8a6a52', '#b39a84'
ACENTO, MIEL, VERDE, ROJO = '#b4532a', '#c98a3a', '#5f7a35', '#b0442f'

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=DM+Sans:wght@400;500;600&display=swap');
.stApp {{ background:{BG}; color:{INK}; font-family:'DM Sans',sans-serif; }}
[data-testid="stHeader"] {{ background:transparent; }}
[data-testid="stHeader"] * {{ color:{MUTED} !important; }}
[data-testid="stSidebarNav"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"],
[data-testid="stExpandSidebarButton"], [data-testid="stSidebar"] {{ display:none; }}
.block-container {{ max-width:920px; padding-top:1.2rem; padding-bottom:4rem; }}
[data-testid="stWidgetLabel"] p {{ color:{INK} !important; font-weight:500; }}
.eyebrow {{ font-size:.7rem; letter-spacing:.2em; text-transform:uppercase; color:{ACENTO}; margin:0; font-weight:600; }}
.titulo {{ font-family:'Fraunces',serif; font-size:2.4rem; font-weight:600; line-height:1.05; color:{INK}; margin:.15rem 0 .3rem; }}
.resumen {{ display:flex; gap:.6rem; margin:.4rem 0 1.1rem; flex-wrap:wrap; }}
.resumen span {{ background:{CARD}; border:1px solid {LINE}; border-radius:999px; padding:.3rem .8rem; font-size:.85rem; color:{MUTED}; }}
.resumen b {{ color:{INK}; }}
[data-testid="stVerticalBlock"] {{ border-color:{LINE} !important; }}
[data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"] {{ background:{CARD}; border-radius:18px;
    box-shadow:0 2px 10px rgba(120,80,40,.06); }}
.ph {{ background:#f6f1eb; border-radius:12px; overflow:hidden; display:flex; justify-content:center; margin-bottom:.6rem; }}
.ph img {{ width:100%; height:280px; object-fit:contain; mix-blend-mode:multiply; }}
.ph.grande img {{ height:360px; }}
.ph.vacia {{ height:230px; align-items:center; font-family:'Fraunces',serif; font-size:3rem; color:{FAINT}; }}
.pn {{ font-family:'Fraunces',serif; font-size:1.35rem; line-height:1.15; color:{INK}; margin:0; }}
.pm {{ font-size:.85rem; color:{MUTED}; margin:.25rem 0 .1rem; }}
.pm b {{ color:{INK}; font-size:1rem; }}
.pmin {{ font-size:.8rem; color:{FAINT}; margin:0 0 .1rem; }}
.precio {{ font-family:'Fraunces',serif; font-size:3.2rem; font-weight:600; color:{INK}; line-height:1; margin:.2rem 0; }}
.tachado {{ font-family:'DM Sans',sans-serif; font-size:1.1rem; color:{FAINT}; text-decoration:line-through; margin-left:.6rem; font-weight:400; }}
.ahorro {{ display:inline-block; background:#f4e2d4; color:{ACENTO}; border-radius:999px; padding:.15rem .6rem; font-size:.8rem; font-weight:600; margin-left:.5rem; vertical-align:middle; }}
.nota {{ font-size:.8rem; color:{MUTED}; margin:.3rem 0; }}
.aviso {{ font-size:.9rem; color:{INK}; background:#f8e7cf; border:1px solid #ecd0a6; border-radius:12px; padding:.7rem .9rem; margin:.4rem 0 .8rem; }}
.ok {{ font-size:.95rem; color:#2f4417; background:#e5ecd2; border:1px solid #cfdcae; border-radius:12px; padding:.7rem .9rem; margin:.2rem 0 1rem; }}
.stock-ok {{ color:{VERDE} !important; font-weight:600; }} .stock-bajo {{ color:{MIEL} !important; font-weight:600; }} .stock-no {{ color:{ROJO} !important; font-weight:600; }}
/* Botones */
.stButton > button, .stFormSubmitButton > button {{ min-height:3rem; border-radius:12px; font-size:1rem; }}
button[kind="primary"], button[kind="primaryFormSubmit"] {{ background:{ACENTO} !important; border-color:{ACENTO} !important; color:#fff !important; font-weight:600; }}
button[kind="primary"] *, button[kind="primaryFormSubmit"] * {{ color:#fff !important; }}
button[kind="primary"]:disabled {{ opacity:.35; }}
button[kind="secondary"] {{ background:{CARD} !important; border:1px solid {LINE} !important; color:{INK} !important; }}
button[kind="secondary"]:hover {{ border-color:{ACENTO} !important; color:{ACENTO} !important; }}
/* Cuero / pago (segmentados) */
[data-testid="stButtonGroup"] button {{ background:{CARD} !important; color:{INK} !important; border-color:{LINE} !important; min-height:2.8rem; }}
[data-testid="stButtonGroup"] button * {{ color:{INK} !important; }}
[data-testid="stButtonGroup"] button[aria-checked="true"] {{ background:{ACENTO} !important; border-color:{ACENTO} !important; }}
[data-testid="stButtonGroup"] button[aria-checked="true"] * {{ color:#fff !important; }}
/* Campos */
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="input"] input, [data-testid="stNumberInputContainer"] {{
    background:{CARD} !important; color:{INK} !important; border-color:{LINE} !important; }}
[data-testid="stSelectbox"] div, [data-testid="stMultiSelect"] div, [data-baseweb="select"] div {{ background-color:{CARD} !important; border-color:{LINE} !important; color:{INK} !important; }}
[data-testid="stSelectbox"] *, [data-testid="stMultiSelect"] div, [data-testid="stMultiSelect"] input, [data-baseweb="select"] *, [data-baseweb="select"] input {{ color:{INK} !important; -webkit-text-fill-color:{INK} !important; }}
[data-baseweb="select"] svg {{ fill:{MUTED} !important; }}
[data-baseweb="select"] [data-baseweb="tag"], [data-baseweb="tag"] {{ background-color:#f4e2d4 !important; }}
[data-baseweb="tag"] * {{ color:{ACENTO} !important; -webkit-text-fill-color:{ACENTO} !important; }}
[data-baseweb="popover"] ul, [data-baseweb="popover"] li, [data-baseweb="menu"], [role="listbox"], [role="option"] {{
    background:{CARD} !important; color:{INK} !important; }}
[role="option"]:hover, [role="option"][aria-selected="true"] {{ background:#f4e2d4 !important; }}
[data-testid="stPopoverBody"] {{ background:{CARD} !important; color:{INK} !important; border:1px solid {LINE}; }}
[data-testid="stTextInputRootElement"] {{ background:{CARD} !important; border-color:{LINE} !important; }}
.stApp input {{ background:transparent !important; color:{INK} !important; -webkit-text-fill-color:{INK} !important;
    font-size:1.05rem; opacity:1 !important; }}
.stApp input::placeholder {{ color:{FAINT} !important; -webkit-text-fill-color:{FAINT} !important; }}
[data-testid="stNumberInputStepDown"], [data-testid="stNumberInputStepUp"] {{ background:{CARD} !important; color:{INK} !important; }}
[data-testid="stNumberInputStepDown"] svg, [data-testid="stNumberInputStepUp"] svg {{ fill:{INK} !important; }}
[data-testid="stSliderThumbValue"] {{ color:{ACENTO} !important; font-weight:600; }}
[data-testid="stSliderTickBar"] * {{ color:{MUTED} !important; }}
/* Expanders y formularios */
[data-testid="stExpander"] details {{ background:{CARD}; border:1px solid {LINE} !important; border-radius:14px; }}
[data-testid="stExpander"] summary {{ background:{CARD} !important; border-radius:14px; }}
[data-testid="stExpander"] summary:hover {{ background:#f8efe3 !important; }}
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary * {{ color:{INK} !important; }}
[data-testid="stExpander"] svg {{ fill:{MUTED}; }}
[data-testid="stForm"] {{ background:{CARD}; border:1px solid {LINE}; border-radius:18px; }}
.vt {{ display:flex; justify-content:space-between; gap:.6rem; font-size:.88rem; padding:.5rem 0; border-bottom:1px dashed {LINE}; }}
.vt.anulada {{ color:{FAINT}; text-decoration:line-through; }}
</style>
"""
