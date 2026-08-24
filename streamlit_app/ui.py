"""
============================================================================
 CINEMATIC UI KIT
============================================================================
Presentation-layer helpers for the Streamlit dashboard: a base theme
(fonts, a drifting animated background, card/section/widget styling), a
live scrolling stats ticker ("moving taskbar"), and JS-driven count-up KPI
cards with animated target-progress bars. Kept separate from app.py so the
page code stays about data, not markup.

Nothing here touches the warehouse or the KPI math — it only renders
values app.py has already computed.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

GREEN = "#22c55e"
AMBER = "#f59e0b"
RED = "#ef4444"
PRIMARY = "#3b82f6"

FONTS = ("@import url('https://fonts.googleapis.com/css2?"
         "family=Sora:wght@600;700;800&family=Inter:wght@400;500;600;700&display=swap');")


# ---------------------------------------------------------------------------
# Small KPI-math helpers shared by app.py
# ---------------------------------------------------------------------------
def fmt_money(x: float) -> str:
    if x is None or pd.isna(x):
        return "$0"
    if abs(x) >= 1_000_000:
        return f"${x/1_000_000:.2f}M"
    if abs(x) >= 1_000:
        return f"${x/1_000:.1f}K"
    return f"${x:,.0f}"


def status_of(ok: bool, warn: bool = False) -> str:
    """Three-tier RAG status: 'on' | 'watch' | 'off'."""
    if ok:
        return "on"
    if warn:
        return "watch"
    return "off"


def goodness_frac(value: float, threshold: float, higher_is_better: bool = True) -> float:
    """0..1 'how close to / past target' meter — symmetric for floor and
    ceiling KPIs, so a fuller bar always means 'better' regardless of
    whether the metric is a floor (revenue) or a ceiling (churn)."""
    if not threshold or value is None or pd.isna(value):
        return 0.0
    ratio = value / threshold if higher_is_better else threshold / max(value, 1e-9)
    return max(0.0, min(1.0, ratio))


def calc_delta(curv: float, prevv: float) -> float | None:
    """Signed % change, or None when there's no meaningful prior value."""
    if prevv in (0, None) or pd.isna(prevv):
        return None
    return (curv - prevv) / abs(prevv) * 100


# ---------------------------------------------------------------------------
# Base theme: fonts, drifting background, card/section/widget styling.
# ---------------------------------------------------------------------------
def inject_base_theme() -> None:
    st.markdown(
        f"""
        <style>
          {FONTS}

          html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
          h1, h2, h3, h4 {{ font-family: 'Sora', sans-serif; letter-spacing: -.01em; }}
          h1 {{
            background: linear-gradient(90deg, #f1f5f9 30%, #93c5fd 55%, #f1f5f9 80%);
            background-size: 200% auto; -webkit-background-clip: text;
            background-clip: text; color: transparent;
            animation: titleShine 7s linear infinite;
          }}
          @keyframes titleShine {{ to {{ background-position: -200% center; }} }}

          .stApp {{
            background: radial-gradient(circle at 15% 0%, #131a2b 0%, #0b0e17 45%, #090b12 100%);
          }}

          /* Drifting cinematic background orbs */
          .orb {{ position: fixed; border-radius: 50%; filter: blur(70px);
                  opacity: .16; pointer-events: none; z-index: 0; }}
          .orb1 {{ width: 480px; height: 480px; top: -120px; left: -100px;
                   background: #3b82f6; animation: driftA 34s ease-in-out infinite; }}
          .orb2 {{ width: 420px; height: 420px; bottom: -140px; right: -80px;
                   background: #7c3aed; animation: driftB 42s ease-in-out infinite; }}
          .orb3 {{ width: 320px; height: 320px; top: 40%; right: 8%;
                   background: #16a34a; animation: driftC 50s ease-in-out infinite; }}
          @keyframes driftA {{ 0%,100% {{transform: translate(0,0);}} 50% {{transform: translate(80px,60px);}} }}
          @keyframes driftB {{ 0%,100% {{transform: translate(0,0);}} 50% {{transform: translate(-70px,-50px);}} }}
          @keyframes driftC {{ 0%,100% {{transform: translate(0,0);}} 50% {{transform: translate(-40px,70px);}} }}

          /* Cinematic intro sweep, once per (re)render */
          .intro-bar {{
            position: fixed; top: 0; left: 0; height: 3px; width: 100%; z-index: 999;
            background: linear-gradient(90deg, #3b82f6, #7c3aed, #16a34a);
            animation: introSweep 1.7s ease forwards;
          }}
          @keyframes introSweep {{
            0% {{ width: 0%; opacity: 1; }} 70% {{ width: 100%; opacity: 1; }}
            100% {{ width: 100%; opacity: 0; }}
          }}

          @keyframes fadeInUp {{
            from {{ opacity: 0; transform: translateY(14px); }}
            to   {{ opacity: 1; transform: translateY(0); }}
          }}

          .section-title {{
            display: flex; align-items: center; gap: 10px; margin: 26px 0 10px 0;
            font-family: 'Sora', sans-serif; font-weight: 700; font-size: 1.2rem;
            color: #e2e8f0; animation: fadeInUp .5s ease both;
          }}
          .section-title .bar {{
            width: 34px; height: 4px; border-radius: 3px; flex: none;
            background: linear-gradient(90deg, #3b82f6, #7c3aed);
            animation: barGrow .7s ease both;
          }}
          @keyframes barGrow {{ from {{ width: 0; }} to {{ width: 34px; }} }}

          .big-insight {{
            background: linear-gradient(120deg, rgba(16,60,38,.55), rgba(10,30,22,.55));
            border: 1px solid #1f6f43; border-radius: 16px; padding: 20px 24px;
            box-shadow: 0 0 30px rgba(34,197,94,.08);
            animation: fadeInUp .7s ease both; position: relative; overflow: hidden;
          }}
          .big-insight::before {{
            content: ""; position: absolute; inset: 0;
            background: linear-gradient(100deg, transparent 20%, rgba(255,255,255,.05) 35%, transparent 50%);
            background-size: 200% 100%; animation: sheen 5s ease-in-out infinite;
          }}
          @keyframes sheen {{ 0% {{background-position: 150% 0;}} 100% {{background-position: -50% 0;}} }}

          .section-note {{ color: #94a3b8; font-size: 0.9rem; }}

          ::-webkit-scrollbar {{ width: 10px; height: 10px; }}
          ::-webkit-scrollbar-track {{ background: #0b0e17; }}
          ::-webkit-scrollbar-thumb {{ background: #263143; border-radius: 6px; }}
          ::-webkit-scrollbar-thumb:hover {{ background: #334155; }}

          [data-testid="stDataFrame"] {{ border-radius: 12px; overflow: hidden; border: 1px solid #263143; }}

          .stButton > button {{ border-radius: 10px; transition: all .2s ease; border: 1px solid #2563eb; }}
          .stButton > button:hover {{ transform: translateY(-1px); box-shadow: 0 4px 16px rgba(37,99,235,.35); }}

          section[data-testid="stSidebar"] {{
            background: linear-gradient(180deg, #0d1220 0%, #0a0d16 100%);
            border-right: 1px solid #1c2333;
          }}
        </style>
        <div class="intro-bar"></div>
        <div class="orb orb1"></div>
        <div class="orb orb2"></div>
        <div class="orb orb3"></div>
        """,
        unsafe_allow_html=True,
    )


def section_header(text: str, icon: str = "") -> None:
    prefix = f"{icon} " if icon else ""
    st.markdown(f"<div class='section-title'><span class='bar'></span>{prefix}{text}</div>",
                unsafe_allow_html=True)


def big_insight(body_html: str) -> None:
    st.markdown(f"<div class='big-insight'>{body_html}</div>", unsafe_allow_html=True)


def live_pill(label: str = "Warehouse fresh") -> str:
    return (
        "<span style='display:inline-flex;align-items:center;gap:7px;"
        "background:#0f2418;border:1px solid #14532d;color:#86efac;"
        "padding:4px 12px;border-radius:999px;font-size:.78rem;font-weight:600;'>"
        "<span style='width:8px;height:8px;border-radius:50%;background:#22c55e;"
        "animation:pulseDot 1.8s infinite;'></span>"
        f"{label}</span>"
        "<style>@keyframes pulseDot{0%{box-shadow:0 0 0 0 rgba(34,197,94,.55);}"
        "70%{box-shadow:0 0 0 8px rgba(34,197,94,0);}100%{box-shadow:0 0 0 0 rgba(34,197,94,0);}}</style>"
    )


# ---------------------------------------------------------------------------
# Scrolling stats ticker — the "moving taskbar"
# ---------------------------------------------------------------------------
def ticker(items: list[tuple[str, str, str]]) -> None:
    """items: (label, value, color-hex) shown in an infinite horizontal scroll."""

    def chip(label: str, value: str, color: str) -> str:
        return (f"<span class='tk-item'><span class='tk-label'>{label}</span>"
                f"<span class='tk-value' style='color:{color}'>{value}</span></span>"
                f"<span class='tk-sep'>•</span>")

    row = "".join(chip(*i) for i in items)
    st.markdown(
        f"""
        <style>
          .tk-wrap {{
            position: relative; overflow: hidden; border-radius: 12px;
            border: 1px solid #1c2333; background: linear-gradient(90deg,#10131d,#0c0f18);
            padding: 10px 0; margin-bottom: 18px;
          }}
          .tk-track {{ display: flex; width: max-content; white-space: nowrap;
                       animation: tkScroll 34s linear infinite; }}
          .tk-wrap:hover .tk-track {{ animation-play-state: paused; }}
          .tk-item {{ display:inline-flex; gap:8px; padding: 0 18px; align-items:baseline; }}
          .tk-label {{ color:#64748b; font-size:.72rem; letter-spacing:.06em; text-transform:uppercase; }}
          .tk-value {{ font-weight: 700; font-size: .92rem; font-family:'Sora',sans-serif; }}
          .tk-sep {{ color:#334155; }}
          @keyframes tkScroll {{ from {{ transform: translateX(0); }} to {{ transform: translateX(-50%); }} }}
        </style>
        <div class="tk-wrap"><div class="tk-track">{row}{row}</div></div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# JS-driven, count-up KPI card grid
# ---------------------------------------------------------------------------
def kpi_row(cards: list[dict[str, Any]], cols: int = 3) -> None:
    """
    Render an animated KPI grid as a single embedded component: values count
    up from 0, status pills pulse, and target-progress bars fill in.

    Each card dict:
      label (str, required), value (float, required)
      kind: 'money' | 'percent' | 'multiplier' | 'int' | 'plain' (default 'plain')
      decimals (int, default 1 for percent/multiplier else 0)
      delta_pct (float | None), delta_good (bool) — MoM change badge
      status: 'on' | 'watch' | 'off' | None — RAG pill
      caption (str) — small grey line under the value
      progress (float 0..1 | None) — animated target-progress bar
    """
    n = len(cards)
    if n == 0:
        return
    cols = max(1, min(cols, n))
    rows = -(-n // cols)  # ceil

    has_caption = any(c.get("caption") for c in cards)
    has_bar = any(c.get("progress") is not None for c in cards)
    card_h = 116 + (20 if has_caption else 0) + (22 if has_bar else 0)
    height = rows * (card_h + 16) + 26

    colors = {"on": GREEN, "watch": AMBER, "off": RED}
    labels = {"on": "ON TARGET", "watch": "WATCH", "off": "OFF TARGET"}

    def esc(s: str) -> str:
        return (s or "").replace("</", "<\\/")

    card_html: list[str] = []
    for i, c in enumerate(cards):
        kind = c.get("kind", "plain")
        decimals = c.get("decimals", 1 if kind in ("percent", "multiplier") else 0)
        status = c.get("status")
        color = colors.get(status, PRIMARY)

        delta_html = ""
        if c.get("delta_pct") is not None:
            dcolor = GREEN if c.get("delta_good", True) else RED
            arrow = "▲" if c["delta_pct"] >= 0 else "▼"
            delta_html = (f"<span class='kdelta' style='color:{dcolor}'>"
                          f"{arrow} {abs(c['delta_pct']):.1f}% MoM</span>")

        pill_html = ""
        if status:
            pulse = "kpulse" if status == "on" else ""
            pill_html = (f"<span class='kpill {pulse}' style='background:{color}22;"
                        f"color:{color};border:1px solid {color}55;'>"
                        f"<span class='kdot' style='background:{color}'></span>"
                        f"{esc(c.get('status_label', labels.get(status, '')))}</span>")

        bar_html = ""
        if c.get("progress") is not None:
            pct = max(0.0, min(1.0, c["progress"])) * 100
            bar_html = (f"<div class='kbar-track'><div class='kbar-fill' "
                       f"data-pct='{pct:.1f}' style='background:{color}'></div></div>")

        caption_html = f"<div class='kcaption'>{esc(c.get('caption', ''))}</div>" if c.get("caption") else ""

        card_html.append(f"""
          <div class="kcard" style="animation-delay:{i*80}ms;border-color:{color}33;">
            <div class="klabel">{esc(c['label'])}</div>
            <div class="kvalue" data-target="{c['value']}" data-kind="{kind}" data-decimals="{decimals}">0</div>
            <div class="ksub">{delta_html}{pill_html}</div>
            {caption_html}
            {bar_html}
          </div>""")

    doc = f"""
    <html><head><style>
      {FONTS}
      * {{ box-sizing: border-box; }}
      body {{ margin:0; background: transparent; font-family: 'Inter', system-ui, sans-serif; }}
      .kgrid {{ display:grid; grid-template-columns: repeat({cols}, 1fr); gap:16px; padding:2px; }}
      .kcard {{
        position: relative; min-height: {card_h}px;
        background: linear-gradient(150deg,#1a2135 0%,#131826 100%);
        border: 1px solid #263143; border-radius: 14px; padding: 16px 18px;
        opacity:0; animation: cardIn .55s ease forwards;
        transition: transform .25s ease, box-shadow .25s ease;
      }}
      .kcard:hover {{ transform: translateY(-4px); box-shadow: 0 10px 26px rgba(0,0,0,.35); }}
      @keyframes cardIn {{ from {{opacity:0; transform:translateY(16px);}} to {{opacity:1; transform:translateY(0);}} }}
      .klabel {{ font-size:.76rem; letter-spacing:.05em; color:#94a3b8; text-transform:uppercase; margin-bottom:6px; }}
      .kvalue {{ font-family:'Sora',sans-serif; font-size:1.7rem; font-weight:700; color:#f1f5f9; line-height:1.15; }}
      .ksub {{ display:flex; align-items:center; gap:8px; margin-top:8px; flex-wrap:wrap; min-height:22px; }}
      .kdelta {{ font-size:.8rem; font-weight:600; }}
      .kpill {{ display:inline-flex; align-items:center; gap:6px; padding:2px 10px; border-radius:999px;
                font-size:.68rem; font-weight:700; letter-spacing:.03em; }}
      .kdot {{ width:6px; height:6px; border-radius:50%; }}
      .kpulse .kdot {{ animation: kdotPulse 1.8s infinite; }}
      @keyframes kdotPulse {{ 0%{{box-shadow:0 0 0 0 currentColor;}} 70%{{box-shadow:0 0 0 6px transparent;}}
                              100%{{box-shadow:0 0 0 0 transparent;}} }}
      .kcaption {{ font-size:.75rem; color:#64748b; margin-top:6px; }}
      .kbar-track {{ margin-top:10px; height:5px; border-radius:3px; background:#1e2536; overflow:hidden; }}
      .kbar-fill {{ height:100%; width:0%; border-radius:3px; transition: width 1.1s cubic-bezier(.22,.9,.32,1); }}
    </style></head>
    <body>
      <div class="kgrid">{"".join(card_html)}</div>
      <script>
        function fmt(v, kind, decimals) {{
          if (kind === 'money') {{
            var a = Math.abs(v);
            if (a >= 1e6) return '$' + (v/1e6).toFixed(2) + 'M';
            if (a >= 1e3) return '$' + (v/1e3).toFixed(1) + 'K';
            return '$' + Math.round(v).toLocaleString();
          }}
          if (kind === 'percent') return (v*100).toFixed(decimals) + '%';
          if (kind === 'multiplier') return v.toFixed(decimals) + '×';
          if (kind === 'int') return Math.round(v).toLocaleString();
          return v.toFixed(decimals);
        }}
        document.querySelectorAll('.kvalue').forEach(function(el, idx) {{
          var target = parseFloat(el.dataset.target) || 0;
          var kind = el.dataset.kind, decimals = parseInt(el.dataset.decimals || '0');
          var dur = 1200, delay = idx * 70, start = null;
          function frame(ts) {{
            if (start === null) start = ts + delay;
            if (ts < start) {{ requestAnimationFrame(frame); return; }}
            var t = Math.min(1, (ts - start) / dur);
            var eased = 1 - Math.pow(1 - t, 3);
            el.textContent = fmt(target * eased, kind, decimals);
            if (t < 1) requestAnimationFrame(frame);
          }}
          requestAnimationFrame(frame);
        }});
        document.querySelectorAll('.kbar-fill').forEach(function(el, idx) {{
          var pct = parseFloat(el.dataset.pct);
          setTimeout(function() {{ el.style.width = pct + '%'; }}, 300 + idx * 70);
        }});
      </script>
    </body></html>
    """
    components.html(doc, height=height, scrolling=False)
