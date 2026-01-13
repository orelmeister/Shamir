"""LLM panel + debate re-ranking for Israeli market scan.

Why this exists
--------------
The basic scanner can produce nonsense momentum outliers (splits, illiquidity, bad data).
This script uses multiple LLMs already present in the repo (DeepSeek + Gemini + optional
local Ollama) to:
  1) flag obvious data quality issues,
  2) score candidates based on fundamentals + business summary + news headlines,
  3) run a short debate round and then produce a consensus ranking.

Outputs
-------
Writes a JSON and a Markdown summary under israeli_long_strategy/llm_outputs/.

Usage
-----
python israeli_long_strategy/llm_market_debate.py \
    --scan-json israeli_long_strategy/market_scan_results_full.json \
  --top-k 40

Environment
-----------
Uses keys from the repo root .env (python-dotenv) if present:
  DEEPSEEK_API_KEY
  GOOGLE_API_KEY
Optional for local model:
  OLLAMA_BASE_URL (default http://localhost:11434)
  OLLAMA_MODEL (default llama3.1:8b)

This is research tooling only; NOT financial advice.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import html as _html
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error
from types import SimpleNamespace

import yfinance as yf

# Optional: PDF report generation (same pattern as weekly_bot + day_trader).
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER

    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False

# Load keys/config from the repo-root .env (best-effort, never prints secrets).
try:
    from dotenv import load_dotenv

    repo_root_env = Path(__file__).resolve().parents[1] / ".env"
    if repo_root_env.exists():
        load_dotenv(repo_root_env)
    else:
        load_dotenv()
except Exception:
    # Script can still run with Ollama-only or already-exported env vars.
    pass

try:
    from langchain_core.messages import HumanMessage, SystemMessage
except Exception:
    HumanMessage = None
    SystemMessage = None


@dataclass
class ModelResult:
    model: str
    raw: str
    parsed: Optional[Dict[str, Any]]
    error: Optional[str] = None


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fmt_money_ils(price: Any) -> str:
    try:
        v = float(price)
    except Exception:
        return ""
    if v <= 0:
        return ""
    if v < 10:
        return f"₪{v:.3f}"
    if v < 100:
        return f"₪{v:.2f}"
    return f"₪{v:,.1f}"


def _fmt_pct(v: Any) -> str:
    try:
        x = float(v)
    except Exception:
        return ""
    return f"{x:+.2f}%"


def _shorten(s: Any, n: int) -> str:
    txt = str(s or "")
    if len(txt) <= n:
        return txt
    return txt[: max(0, n - 1)] + "…"


def _build_rank_index(
    *,
    ranked_rows: List[Dict[str, Any]],
    key: str = "symbol",
) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for r in ranked_rows:
        if not isinstance(r, dict):
            continue
        sym = r.get(key)
        if not sym:
            continue
        out[str(sym)] = r
    return out


def _render_html_report(
    *,
    title: str,
    subtitle: str,
    artifacts_dir: Path,
    universe_rows: int,
    scan_path: Path,
    ranked_rows: List[Dict[str, Any]],
    candidates: List[Dict[str, Any]],
    out_path: Path,
    disclaimer: str,
) -> None:
    """Write a standalone HTML report (no external deps)."""

    by_symbol = {c.get("symbol"): c for c in candidates if isinstance(c, dict) and c.get("symbol")}
    # Note: ranked_rows is authoritative for ordering; candidates provide enrichment.

    rows_html: List[str] = []
    for i, r in enumerate(ranked_rows, start=1):
        sym = str(r.get("symbol") or "")
        c = by_symbol.get(sym) or {}
        name = c.get("name") or r.get("name") or ""
        price = c.get("price") if "price" in c else r.get("price")
        mom = c.get("momentum_6m_pct") if "momentum_6m_pct" in c else r.get("momentum_6m_pct")
        sector = c.get("sector") or ""
        verdict = (r.get("verdict") or r.get("best_verdict") or "").upper()
        points = r.get("avg_points") if "avg_points" in r else r.get("points")
        conf = r.get("confidence")

        yfin = f"https://finance.yahoo.com/quote/{_html.escape(sym)}"
        rows_html.append(
            "<tr>"
            f"<td class='rank'>{i}</td>"
            f"<td class='sym'><a href='{yfin}' target='_blank' rel='noreferrer'>{_html.escape(sym)}</a></td>"
            f"<td class='name'>{_html.escape(_shorten(name, 60))}</td>"
            f"<td class='price'>{_html.escape(_fmt_money_ils(price))}</td>"
            f"<td class='mom'>{_html.escape(_fmt_pct(mom))}</td>"
            f"<td class='sector'>{_html.escape(_shorten(sector, 40))}</td>"
            f"<td class='verdict'>{_html.escape(verdict)}</td>"
            f"<td class='points'>{_html.escape(str(round(float(points), 2)) if points is not None else '')}</td>"
            f"<td class='conf'>{_html.escape(str(conf) if conf is not None else '')}</td>"
            f"<td><a class='jump' href='#d-{_html.escape(sym)}'>details</a></td>"
            "</tr>"
        )

    details_html: List[str] = []
    for r in ranked_rows[: min(30, len(ranked_rows))]:
        sym = str(r.get("symbol") or "")
        c = by_symbol.get(sym) or {}
        k = c.get("kosher") or {}
        kosher_flag = k.get("kosher_candidate")
        kosher_conf = k.get("confidence")
        kosher_reasons = k.get("reasons") or []
        kosher_notes = k.get("notes") or []

        summary = c.get("business_summary") or ""
        news = c.get("news") or []
        thesis = r.get("thesis") or ""
        red_flags = r.get("red_flags") or []

        red_flags_html = "".join([f"<li>{_html.escape(str(x))}</li>" for x in red_flags])
        reasons_html = "".join(
            [
                f"<li>{_html.escape(str(x))}</li>"
                for x in (kosher_reasons[:6] if isinstance(kosher_reasons, list) else [])
            ]
        )
        notes_html = "".join(
            [
                f"<li>{_html.escape(str(x))}</li>"
                for x in (kosher_notes[:6] if isinstance(kosher_notes, list) else [])
            ]
        )
        headlines_html = "".join(
            [
                f"<li>{_html.escape(str(n.get('title') or n))}</li>"
                for n in (news[:6] if isinstance(news, list) else [])
            ]
        )

        verdict_label = str(r.get("verdict") or r.get("best_verdict") or "").upper()

        section_html = (
            f"<section class='card' id='d-{_html.escape(sym)}'>"
            f"<h3>{_html.escape(sym)} <span class='chip'>{_html.escape(verdict_label)}</span></h3>"
            "<div class='grid'>"
            f"<div><b>Name</b><div>{_html.escape(str(c.get('name') or ''))}</div></div>"
            f"<div><b>Price</b><div>{_html.escape(_fmt_money_ils(c.get('price')))}</div></div>"
            f"<div><b>6M momentum</b><div>{_html.escape(_fmt_pct(c.get('momentum_6m_pct')))}</div></div>"
            f"<div><b>Sector</b><div>{_html.escape(str(c.get('sector') or ''))}</div></div>"
            "</div>"
            "<div class='two-col'>"
            f"<div><h4>Thesis</h4><p>{_html.escape(str(thesis))}</p></div>"
            f"<div><h4>Red flags</h4><ul>{red_flags_html}</ul></div>"
            "</div>"
            "<h4>Business summary</h4>"
            f"<p class='mono'>{_html.escape(_shorten(summary, 1200))}</p>"
            "<h4>Kosher screen (heuristic)</h4>"
            f"<p>Candidate: <b>{_html.escape(str(bool(kosher_flag)))}</b> | confidence: <b>{_html.escape(str(kosher_conf))}</b></p>"
            f"<ul>{reasons_html}</ul>"
        )
        if kosher_notes:
            section_html += f"<h4>Notes</h4><ul>{notes_html}</ul>"
        if news:
            section_html += f"<h4>Recent headlines</h4><ul>{headlines_html}</ul>"
        section_html += "</section>"
        details_html.append(section_html)

    html_text = f"""<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8' />
  <meta name='viewport' content='width=device-width, initial-scale=1' />
  <title>{_html.escape(title)}</title>
  <style>
    :root {{
      --bg: #0b1020;
      --card: #111a33;
      --text: #e9ecf5;
      --muted: #a9b4d0;
      --accent: #6ee7ff;
      --accent2: #a78bfa;
      --good: #34d399;
      --warn: #fbbf24;
      --bad: #fb7185;
      --border: rgba(255,255,255,0.08);
    }}
    body {{ margin: 0; background: linear-gradient(180deg, var(--bg), #060814); color: var(--text); font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; }}
    .wrap {{ max-width: 1150px; margin: 0 auto; padding: 28px 18px 60px; }}
    header {{ margin-bottom: 18px; }}
    h1 {{ font-size: 26px; margin: 0 0 6px; letter-spacing: 0.2px; }}
    .sub {{ color: var(--muted); font-size: 13px; line-height: 1.35; }}
    .pill {{ display: inline-block; padding: 6px 10px; border: 1px solid var(--border); border-radius: 999px; margin-right: 8px; color: var(--muted); font-size: 12px; }}
    .card {{ background: rgba(17,26,51,0.92); border: 1px solid var(--border); border-radius: 14px; padding: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.25); }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 10px; margin: 10px 0 6px; }}
    .grid > div {{ background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 12px; padding: 10px; }}
    .grid b {{ color: var(--muted); font-weight: 600; font-size: 12px; }}
    .grid div div {{ margin-top: 4px; font-size: 13px; }}
    table {{ width: 100%; border-collapse: collapse; overflow: hidden; border-radius: 12px; }}
    thead th {{ text-align: left; font-size: 12px; color: var(--muted); font-weight: 600; padding: 10px 10px; border-bottom: 1px solid var(--border); }}
    tbody td {{ padding: 10px 10px; border-bottom: 1px solid var(--border); font-size: 13px; }}
    tbody tr:hover {{ background: rgba(255,255,255,0.03); }}
    .rank {{ width: 40px; color: var(--muted); }}
    .sym a {{ color: var(--accent); text-decoration: none; }}
    .sym a:hover {{ text-decoration: underline; }}
    .jump {{ color: var(--accent2); text-decoration: none; }}
    .jump:hover {{ text-decoration: underline; }}
    .chip {{ display: inline-block; margin-left: 10px; padding: 4px 8px; border-radius: 999px; font-size: 12px; background: rgba(110,231,255,0.12); border: 1px solid rgba(110,231,255,0.25); color: var(--accent); }}
    h2 {{ margin: 18px 0 10px; font-size: 18px; }}
    h3 {{ margin: 0 0 10px; font-size: 16px; }}
    h4 {{ margin: 12px 0 6px; font-size: 13px; color: var(--muted); }}
    .mono {{ color: #d7def5; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; white-space: pre-wrap; }}
    .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 6px; }}
    ul {{ margin: 6px 0 0 18px; color: #d7def5; }}
    p {{ margin: 6px 0 0; color: #d7def5; }}
    .footer {{ margin-top: 20px; color: var(--muted); font-size: 12px; }}
    @media (max-width: 980px) {{ .grid {{ grid-template-columns: repeat(2, minmax(0,1fr)); }} .two-col {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <div class='wrap'>
    <header>
      <h1>{_html.escape(title)}</h1>
      <div class='sub'>{_html.escape(subtitle)}</div>
      <div style='margin-top:10px'>
        <span class='pill'>Universe rows: {universe_rows}</span>
        <span class='pill'>Scan: {_html.escape(str(scan_path))}</span>
        <span class='pill'>Artifacts: {_html.escape(str(artifacts_dir))}</span>
      </div>
    </header>

    <section class='card'>
      <h2>Ranked shortlist</h2>
      <div class='sub'>{_html.escape(disclaimer)}</div>
      <div style='margin-top: 12px; overflow-x:auto'>
        <table>
          <thead>
            <tr>
              <th>#</th><th>Symbol</th><th>Name</th><th>Price</th><th>6M</th><th>Sector</th><th>Verdict</th><th>Points</th><th>Conf</th><th></th>
            </tr>
          </thead>
          <tbody>
            {"".join(rows_html)}
          </tbody>
        </table>
      </div>
    </section>

    <h2 style='margin-top: 22px'>Candidate details (top {min(30, len(ranked_rows))})</h2>
    {"".join(details_html)}

    <div class='footer'>Generated by israeli_long_strategy/llm_market_debate.py • { _html.escape(datetime.now(timezone.utc).isoformat()) } • Not financial advice.</div>
  </div>
</body>
</html>
"""
    _write_text(out_path, html_text)


def _render_pdf_report(
    *,
    title: str,
    artifacts_dir: Path,
    universe_rows: int,
    scan_path: Path,
    ranked_rows: List[Dict[str, Any]],
    candidates: List[Dict[str, Any]],
    out_path: Path,
    disclaimer: str,
) -> Optional[Path]:
    """Write a PDF report using ReportLab (if installed)."""
    if not REPORTLAB_AVAILABLE:
        return None

    by_symbol = {c.get("symbol"): c for c in candidates if isinstance(c, dict) and c.get("symbol")}

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=letter,
        rightMargin=0.6 * inch,
        leftMargin=0.6 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title=title,
    )
    styles = getSampleStyleSheet()
    story: List[Any] = []

    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontSize=18,
        textColor=colors.HexColor("#1f3a8a"),
        spaceAfter=10,
        alignment=TA_CENTER,
    )
    heading_style = ParagraphStyle(
        "Heading",
        parent=styles["Heading2"],
        fontSize=13,
        textColor=colors.HexColor("#111827"),
        spaceBefore=12,
        spaceAfter=8,
    )

    story.append(Paragraph(_html.escape(title), title_style))
    story.append(Paragraph(f"<i>Generated: {datetime.now().strftime('%B %d, %Y %H:%M UTC')}</i>", styles["Normal"]))
    story.append(Spacer(1, 0.18 * inch))
    story.append(Paragraph(_html.escape(disclaimer), styles["Normal"]))
    story.append(Spacer(1, 0.20 * inch))

    # Summary table
    summary_data = [
        ["Metric", "Value"],
        ["Universe rows", str(universe_rows)],
        ["Scan JSON", str(scan_path)],
        ["Artifacts", str(artifacts_dir)],
        ["Ranked rows", str(len(ranked_rows))],
    ]
    summary_table = Table(summary_data, colWidths=[2.2 * inch, 4.8 * inch])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a8a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 11),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f9fafb")),
                ("FONTSIZE", (0, 1), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(summary_table)

    story.append(Spacer(1, 0.22 * inch))
    story.append(Paragraph("Top picks (shortlist)", heading_style))

    # Top table
    top_data = [["#", "Symbol", "Verdict", "Price", "6M", "Sector"]]
    for i, r in enumerate(ranked_rows[:20], start=1):
        sym = str(r.get("symbol") or "")
        c = by_symbol.get(sym) or {}
        verdict = (r.get("verdict") or r.get("best_verdict") or "").upper()
        top_data.append(
            [
                str(i),
                sym,
                verdict,
                _fmt_money_ils(c.get("price") if "price" in c else r.get("price")),
                _fmt_pct(c.get("momentum_6m_pct") if "momentum_6m_pct" in c else r.get("momentum_6m_pct")),
                _shorten(c.get("sector") or "", 32),
            ]
        )

    top_table = Table(top_data, colWidths=[0.35 * inch, 1.05 * inch, 0.8 * inch, 0.9 * inch, 0.8 * inch, 2.9 * inch])
    top_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
            ]
        )
    )
    story.append(top_table)

    # Candidate detail pages (top 10)
    story.append(PageBreak())
    story.append(Paragraph("Candidate details (top 10)", heading_style))
    for i, r in enumerate(ranked_rows[:10], start=1):
        sym = str(r.get("symbol") or "")
        c = by_symbol.get(sym) or {}
        name = str(c.get("name") or "")
        summary = _shorten(c.get("business_summary") or "", 1500)
        thesis = _shorten(r.get("thesis") or "", 600)
        red_flags = r.get("red_flags") or []
        kosher = c.get("kosher") or {}

        story.append(Paragraph(f"{i}. <b>{_html.escape(sym)}</b> — {_html.escape(name)}", styles["Heading3"]))
        story.append(Spacer(1, 0.08 * inch))

        facts = [
            ["Price", _fmt_money_ils(c.get("price"))],
            ["6M momentum", _fmt_pct(c.get("momentum_6m_pct"))],
            ["Sector", str(c.get("sector") or "")],
            ["Industry", str(c.get("industry") or "")],
            ["Verdict", str((r.get("verdict") or r.get("best_verdict") or "")).upper()],
            ["Kosher candidate (heuristic)", str(bool(kosher.get("kosher_candidate")))],
            ["Kosher confidence", str(kosher.get("confidence"))],
        ]
        facts_table = Table(facts, colWidths=[2.1 * inch, 4.9 * inch])
        facts_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef2ff")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(facts_table)
        story.append(Spacer(1, 0.10 * inch))

        if thesis:
            story.append(Paragraph("<b>Thesis</b>", styles["Normal"]))
            story.append(Paragraph(_html.escape(thesis).replace("\n", "<br/>"), styles["Normal"]))
            story.append(Spacer(1, 0.08 * inch))

        if red_flags:
            story.append(Paragraph("<b>Red flags</b>", styles["Normal"]))
            for rf in red_flags[:8]:
                story.append(Paragraph(f"• {_html.escape(str(rf))}", styles["Normal"]))
            story.append(Spacer(1, 0.08 * inch))

        if summary:
            story.append(Paragraph("<b>Business summary</b>", styles["Normal"]))
            story.append(Paragraph(_html.escape(summary).replace("\n", "<br/>"), styles["Normal"]))

        if i < min(10, len(ranked_rows)):
            story.append(Spacer(1, 0.18 * inch))
            story.append(Paragraph("─" * 80, styles["Normal"]))
            story.append(Spacer(1, 0.18 * inch))

    doc.build(story)
    return out_path


_JSON_RE = re.compile(r"\{[\s\S]*\}\s*$")


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None

    # Remove code fences if present
    cleaned = text.strip()
    cleaned = re.sub(r"^```(json)?\s*", "", cleaned)
    cleaned = re.sub(r"```\s*$", "", cleaned)

    # Try direct parse first
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # Try to grab the last JSON object in the response
    m = _JSON_RE.search(cleaned)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None

    return None


def _looks_like_required_schema(obj: Any) -> bool:
    """Validate the expected schema for model outputs.

    Expected keys:
      - model (string)
      - ranked (list of objects)
      - notes (list of strings)
    """

    if not isinstance(obj, dict):
        return False
    ranked = obj.get("ranked")
    notes = obj.get("notes")
    if not isinstance(ranked, list):
        return False
    if notes is not None and not isinstance(notes, list):
        return False
    # If ranked is empty, still accept as valid (it may be the model's view).
    required_fields = {"symbol", "verdict", "score", "confidence", "thesis", "red_flags", "data_quality"}
    for r in ranked[:5]:
        if not isinstance(r, dict):
            return False
        if not required_fields.issubset(set(r.keys())):
            return False
    return True


def _repair_to_schema(
    model_name: str,
    model: Any,
    *,
    candidates: List[Dict[str, Any]],
    content: str,
    timeout_s: int,
    cloud_timeout_mode: str,
) -> ModelResult:
    repair_prompt = (
        "You MUST output valid JSON only.\n"
        "Convert the following content into VALID JSON that EXACTLY matches this schema:\n\n"
        "{\n"
        "  \"model\": string,\n"
        "  \"ranked\": [\n"
        "    {\n"
        "      \"symbol\": string,\n"
        "      \"verdict\": \"BUY\"|\"WATCH\"|\"AVOID\",\n"
        "      \"score\": number,\n"
        "      \"confidence\": number,\n"
        "      \"thesis\": string,\n"
        "      \"red_flags\": [string],\n"
        "      \"data_quality\": \"GOOD\"|\"MIXED\"|\"POOR\"\n"
        "    }\n"
        "  ],\n"
        "  \"notes\": [string]\n"
        "}\n\n"
        "Rules:\n"
        "- Output JSON only (no markdown, no commentary).\n"
        "- Do not add symbols not in the candidate list.\n"
        "- Ensure notes is a list (can be empty).\n\n"
        f"Candidate symbols: {[c.get('symbol') for c in candidates]}\n\n"
        f"Content to convert:\n{content}"
    )
    print(f"[LLM] Repair-to-schema -> {model_name}")
    if model_name in ("deepseek", "gemini") and cloud_timeout_mode == "process":
        return _invoke_cloud_model_in_subprocess(model_name, repair_prompt, timeout_s=timeout_s)
    return _invoke_with_timeout(model_name, model, repair_prompt, timeout_s=timeout_s)


def _safe_float(v) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _score_seed(row: Dict[str, Any]) -> float:
    """Seed score for picking candidates before LLM review.

    We *intentionally* downweight crazy outliers.
    """

    mom = _safe_float(row.get("momentum_6m_pct"))
    if mom is None:
        mom = -999.0

    # Penalize absurd outliers (very often data artifacts)
    if mom > 500:
        mom = 500 - (mom - 500) * 0.2

    kosher = row.get("kosher") or {}
    kosher_flag = 1.0 if kosher.get("kosher_candidate") else 0.0
    conf = _safe_float(kosher.get("confidence")) or 0.0

    return (kosher_flag * 100.0) + (conf * 10.0) + mom


def _pick_candidates(scan: Dict[str, Any], top_k: int) -> List[Dict[str, Any]]:
    results = scan.get("results") or []
    usable = [r for r in results if r.get("symbol") and not r.get("error")]
    usable_sorted = sorted(usable, key=_score_seed, reverse=True)
    return usable_sorted[:top_k]


def _pick_universe(scan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return all usable scan rows, seed-sorted.

    We sort by a conservative seed score so that early batches tend to contain the
    most promising candidates. This helps if you abort early due to rate limits.
    """

    results = scan.get("results") or []
    usable = [r for r in results if r.get("symbol") and not r.get("error")]
    return sorted(usable, key=_score_seed, reverse=True)


def _fetch_enrichment(symbol: str) -> Dict[str, Any]:
    """Fetch a compact fundamental snapshot from yfinance."""

    t = yf.Ticker(symbol)
    info = t.info or {}

    def get(*keys):
        for k in keys:
            v = info.get(k)
            if v is not None and v != "":
                return v
        return None

    snap = {
        "symbol": symbol,
        "shortName": get("shortName", "longName"),
        "sector": get("sector"),
        "industry": get("industry"),
        "country": get("country"),
        "currency": get("currency"),
        "marketCap": get("marketCap"),
        "enterpriseValue": get("enterpriseValue"),
        "trailingPE": get("trailingPE"),
        "forwardPE": get("forwardPE"),
        "priceToBook": get("priceToBook"),
        "dividendYield": get("dividendYield"),
        "profitMargins": get("profitMargins"),
        "revenueGrowth": get("revenueGrowth"),
        "earningsGrowth": get("earningsGrowth"),
        "beta": get("beta"),
        "averageVolume": get("averageVolume", "averageVolume10days"),
        "quoteType": get("quoteType"),
        "exchange": get("exchange"),
        "website": get("website"),
    }

    # Very lightweight volatility / split sanity check
    try:
        hist = t.history(period="6mo", auto_adjust=True)
        if hist is not None and not hist.empty:
            start = _safe_float(hist["Close"].iloc[0])
            last = _safe_float(hist["Close"].iloc[-1])
            if start and last and start != 0:
                snap["momentum_6m_pct_adjusted"] = round(((last - start) / start) * 100.0, 2)
    except Exception:
        pass

    return snap


def _build_candidate_rows(
    candidates: List[Dict[str, Any]],
    enrich: Dict[str, Dict[str, Any]],
    *,
    summary_chars: int = 600,
    headline_count: int = 5,
) -> List[Dict[str, Any]]:
    """Build the candidate rows payload used by LLM prompts."""

    rows: List[Dict[str, Any]] = []
    for r in candidates:
        sym = r.get("symbol")
        e = enrich.get(sym) or {}
        news = r.get("news") or []
        headlines = [n.get("title") for n in news if n.get("title")][: max(0, int(headline_count))]
        rows.append(
            {
                "symbol": sym,
                "name": r.get("name"),
                "sector": r.get("sector"),
                "industry": r.get("industry"),
                "price": r.get("price"),
                "currency": r.get("currency"),
                "momentum_6m_pct": r.get("momentum_6m_pct"),
                "marketCap": e.get("marketCap"),
                "avgVolume": e.get("averageVolume"),
                "trailingPE": e.get("trailingPE"),
                "forwardPE": e.get("forwardPE"),
                "priceToBook": e.get("priceToBook"),
                "profitMargins": e.get("profitMargins"),
                "revenueGrowth": e.get("revenueGrowth"),
                "earningsGrowth": e.get("earningsGrowth"),
                "momentum_6m_pct_adjusted": e.get("momentum_6m_pct_adjusted"),
                "business_summary": (r.get("business_summary") or "")[: max(0, int(summary_chars))],
                "news_headlines": headlines,
            }
        )

    return rows


def _build_prompt(
    candidates: List[Dict[str, Any]],
    enrich: Dict[str, Dict[str, Any]],
    *,
    summary_chars: int = 600,
    headline_count: int = 5,
) -> str:
    """Create a compact prompt that stays grounded in data."""

    payload = json.dumps(
        _build_candidate_rows(candidates, enrich, summary_chars=summary_chars, headline_count=headline_count),
        ensure_ascii=False,
    )

    return (
        "You are an investment research analyst. This is NOT financial advice; it is screening. "
        "Your job: produce a ranked shortlist that is robust against data artifacts and microcap traps.\n\n"
        "You are given JSON rows of Israeli-listed tickers (Yahoo .TA) with basic data, a short business summary, "
        "and up to 5 recent headlines.\n\n"
        "Rules:\n"
        "- DO NOT rank purely on momentum. Treat extreme momentum (e.g., > 300% in 6 months) as suspicious unless fundamentals/news support it.\n"
        "- Penalize illiquidity (low averageVolume), missing marketCap, penny-like prices, and data inconsistencies (momentum_6m_pct vs momentum_6m_pct_adjusted).\n"
        "- Focus on business quality, durability, balance-sheet risk signals (if absent, mention uncertainty), and recent headlines.\n"
        "- Output MUST be valid JSON only (no markdown), matching the schema below.\n\n"
        "Schema:\n"
        "{\n"
        "  \"model\": string,\n"
        "  \"ranked\": [\n"
        "    {\n"
        "      \"symbol\": string,\n"
        "      \"verdict\": \"BUY\"|\"WATCH\"|\"AVOID\",\n"
        "      \"score\": number,\n"
        "      \"confidence\": number,\n"
        "      \"thesis\": string,\n"
        "      \"red_flags\": [string],\n"
        "      \"data_quality\": \"GOOD\"|\"MIXED\"|\"POOR\"\n"
        "    }\n"
        "  ],\n"
        "  \"notes\": [string]\n"
        "}\n\n"
        f"Candidate rows JSON:\n{payload}"
    )


class _DeepSeekHTTPChat:
    """Minimal DeepSeek chat client (OpenAI-compatible) without openai/langchain dependencies.

    DeepSeek exposes an OpenAI-compatible Chat Completions API. Using urllib keeps this script
    resilient to dependency churn and avoids heavy imports that can hang on some environments.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.deepseek.com",
        temperature: float = 0.1,
        request_timeout_s: int = 60,
    ):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._temperature = temperature
        self._timeout_s = int(request_timeout_s)

    def invoke(self, input_: Any):
        # Accept either a prompt string or LangChain message objects.
        messages: List[Dict[str, str]] = []
        if isinstance(input_, str):
            messages = [{"role": "user", "content": input_}]
        elif isinstance(input_, list):
            for m in input_:
                role = "user"
                m_type = getattr(m, "type", None)
                if m_type == "system":
                    role = "system"
                elif m_type in ("human", "user"):
                    role = "user"
                elif m_type == "assistant":
                    role = "assistant"
                content = getattr(m, "content", None)
                if content is None:
                    content = str(m)
                messages.append({"role": role, "content": str(content)})
        else:
            messages = [{"role": "user", "content": str(input_)}]

        body = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
        }

        url = f"{self._base_url}/chat/completions"
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                details = e.read().decode("utf-8", errors="replace")
            except Exception:
                details = str(e)
            raise RuntimeError(f"deepseek_http_error: {e.code} {e.reason}: {details}")
        except Exception as e:
            raise RuntimeError(f"deepseek_http_request_failed: {e}")

        try:
            content = payload["choices"][0]["message"]["content"]
        except Exception:
            raise RuntimeError(f"deepseek_http_bad_response: {payload}")

        return SimpleNamespace(content=content)


def _init_deepseek_model() -> Any:
    """Create a DeepSeek model client.

    Default: lightweight HTTP client (avoids openai/langchain imports that can be slow/hang).
    Set ISRAEL_DEEPSEEK_BACKEND=langchain to force langchain_deepseek.
    """

    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    if not deepseek_key:
        raise RuntimeError("DEEPSEEK_API_KEY not set")

    backend = (os.getenv("ISRAEL_DEEPSEEK_BACKEND") or "http").strip().lower()
    model_name = os.getenv("ISRAEL_LLM_DEEPSEEK_MODEL", "deepseek-reasoner")
    temperature = 0.1

    if backend in ("http", "urllib", "requests"):
        base_url = os.getenv("ISRAEL_DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        req_timeout_s = int(os.getenv("ISRAEL_DEEPSEEK_HTTP_TIMEOUT_S", "60"))
        return _DeepSeekHTTPChat(
            api_key=deepseek_key,
            model=model_name,
            base_url=base_url,
            temperature=temperature,
            request_timeout_s=req_timeout_s,
        )

    # Fallback to langchain-deepseek (may require openai dependencies)
    from langchain_deepseek import ChatDeepSeek

    return ChatDeepSeek(model=model_name, temperature=temperature)


def _init_models(allowed: Optional[set[str]] = None) -> Dict[str, Any]:
    """Initialize only the requested models.

    By default we prefer cloud models (DeepSeek/Gemini). Ollama is intentionally
    opt-in because it is local and can be slow.
    """

    models: Dict[str, Any] = {}

    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    google_key = os.getenv("GOOGLE_API_KEY")

    print(f"DEEPSEEK_API_KEY set: {bool(deepseek_key)}")
    print(f"GOOGLE_API_KEY set: {bool(google_key)}")

    # DeepSeek
    if (allowed is None or "deepseek" in allowed) and deepseek_key:
        try:
            models["deepseek"] = _init_deepseek_model()
            print("[LLM] DeepSeek initialized")
        except Exception:
            print("[LLM] DeepSeek NOT available (import/init failed)")

    # Gemini
    if (allowed is None or "gemini" in allowed) and google_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI

            models["gemini"] = ChatGoogleGenerativeAI(model=os.getenv("ISRAEL_LLM_GEMINI_MODEL", "gemini-2.5-flash"), temperature=0.1)
            print("[LLM] Gemini initialized")
        except Exception:
            print("[LLM] Gemini NOT available (import/init failed)")

    # Local Ollama is opt-in only.
    if allowed is None or "ollama" in allowed:
        try:
            from langchain_ollama import ChatOllama

            models["ollama"] = ChatOllama(model=os.getenv("OLLAMA_MODEL", "llama3.1:8b"))
            print("[LLM] Ollama initialized")
        except Exception:
            # We'll still allow the script to run with cloud models only.
            print("[LLM] Ollama NOT available (import/init failed)")

    return models


def _invoke(model_name: str, model: Any, prompt: str) -> ModelResult:
    try:
        if SystemMessage is not None and HumanMessage is not None:
            msgs = [
                SystemMessage(content="You are strict about returning JSON only."),
                HumanMessage(content=prompt),
            ]
            resp = model.invoke(msgs)
            raw = getattr(resp, "content", None) or str(resp)
        else:
            resp = model.invoke(prompt)
            raw = getattr(resp, "content", None) or str(resp)

        parsed = _extract_json(raw)
        return ModelResult(model=model_name, raw=raw, parsed=parsed)
    except Exception as e:
        return ModelResult(model=model_name, raw="", parsed=None, error=str(e))


def _invoke_with_timeout(model_name: str, model: Any, prompt: str, *, timeout_s: int) -> ModelResult:
    """Invoke a model with a wall-clock timeout.

    Some hosted LLM calls can hang due to network or provider issues. We prefer a best-effort
    pipeline that still writes artifacts.
    """

    ex = ThreadPoolExecutor(max_workers=1)
    fut = ex.submit(_invoke, model_name, model, prompt)
    try:
        return fut.result(timeout=timeout_s)
    except Exception as e:
        # Covers TimeoutError and any executor issues.
        try:
            fut.cancel()
        except Exception:
            pass
        try:
            ex.shutdown(wait=False, cancel_futures=True)
        except Exception:
            # Older Python may not support cancel_futures.
            try:
                ex.shutdown(wait=False)
            except Exception:
                pass
        return ModelResult(model=model_name, raw="", parsed=None, error=f"invoke_failed_or_timed_out: {e}")
    finally:
        # If we got a result quickly, clean shutdown.
        try:
            ex.shutdown(wait=False, cancel_futures=True)
        except Exception:
            try:
                ex.shutdown(wait=False)
            except Exception:
                pass


def _invoke_cloud_model_in_subprocess(model_name: str, prompt: str, *, timeout_s: int) -> ModelResult:
    """Invoke a cloud LLM in a child process so we can hard-timeout.

    Threads cannot reliably stop a hung network call if the underlying client retries forever.
    A subprocess can be terminated.
    """

    q: mp.Queue = mp.Queue()
    p = mp.Process(target=_cloud_invoke_worker, args=(q, model_name, prompt))
    p.daemon = True
    p.start()
    p.join(timeout=timeout_s)

    if p.is_alive():
        try:
            p.terminate()
        except Exception:
            pass
        p.join(timeout=5)
        return ModelResult(model=model_name, raw="", parsed=None, error=f"timeout_after_{timeout_s}s")

    try:
        payload = q.get_nowait()
        return ModelResult(model=payload.get("model", model_name), raw=payload.get("raw", ""), parsed=payload.get("parsed"), error=payload.get("error"))
    except Exception:
        return ModelResult(model=model_name, raw="", parsed=None, error="no_result_from_subprocess")


def _cloud_invoke_worker(q: "mp.Queue", model_name: str, prompt: str):
    """Subprocess entrypoint for DeepSeek/Gemini calls (must be module-scope for Windows spawn)."""

    try:
        if model_name == "deepseek":
            m = _init_deepseek_model()
        elif model_name == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI

            m = ChatGoogleGenerativeAI(model=os.getenv("ISRAEL_LLM_GEMINI_MODEL", "gemini-2.5-flash"), temperature=0.1)
        else:
            raise RuntimeError(f"Unsupported cloud model: {model_name}")

        r = _invoke(model_name, m, prompt)
        q.put({"model": r.model, "raw": r.raw, "parsed": r.parsed, "error": r.error})
    except Exception as e:
        q.put({"model": model_name, "raw": "", "parsed": None, "error": str(e)})


def _debate_round(
    base_outputs: Dict[str, Dict[str, Any]],
    models: Dict[str, Any],
    candidates: List[Dict[str, Any]],
) -> Dict[str, ModelResult]:
    critique_prompt = (
        "You are participating in a multi-analyst debate. You will be shown other models' JSON outputs. "
        "Your task: identify weak reasoning, missed red-flags, and propose an improved ranking.\n\n"
        "Constraints:\n"
        "- Stay grounded in the provided candidate data; do not invent financial statements.\n"
        "- Be extra suspicious of extreme momentum and low liquidity.\n"
        "- Output JSON only, same schema as before.\n\n"
        f"Candidate symbols: {[c.get('symbol') for c in candidates]}\n\n"
        f"Other model outputs JSON: {json.dumps(base_outputs, ensure_ascii=False)}"
    )

    results: Dict[str, ModelResult] = {}
    for name, m in models.items():
        results[name] = _invoke(name, m, critique_prompt)
    return results


def _choose_consensus_model(models: Dict[str, Any]) -> Optional[str]:
    for pref in ("deepseek", "gemini", "ollama"):
        if pref in models:
            return pref
    return None


def _normalize_models(models: Dict[str, Any], requested_csv: str) -> Dict[str, Any]:
    requested = [m.strip().lower() for m in (requested_csv or "").split(",") if m.strip()]
    if not requested:
        return models
    return {k: v for k, v in models.items() if k in requested}


def _parse_model_csv(csv: str) -> List[str]:
    return [m.strip().lower() for m in (csv or "").split(",") if m.strip()]


def _debate_pipeline(
    *,
    candidates: List[Dict[str, Any]],
    enrich: Dict[str, Dict[str, Any]],
    models: Dict[str, Any],
    timeout_s: int,
    rounds: int,
    summary_chars: int,
    headline_count: int,
    cloud_timeout_mode: str,
) -> Dict[str, Any]:
    """Run round1/round2 (optional) and consensus for a candidate set.

    Returns a dict suitable for JSON persistence.
    """

    candidate_rows_json = json.dumps(
        _build_candidate_rows(candidates, enrich, summary_chars=summary_chars, headline_count=headline_count),
        ensure_ascii=False,
    )
    prompt = _build_prompt(candidates, enrich, summary_chars=summary_chars, headline_count=headline_count)

    cloud_timeout_mode = (cloud_timeout_mode or "thread").strip().lower()
    if cloud_timeout_mode not in ("thread", "process"):
        cloud_timeout_mode = "thread"

    # Round 1: independent analyses
    round1: Dict[str, ModelResult] = {}
    for name, m in models.items():
        print(f"[LLM] Round 1 -> {name}")
        if name in ("deepseek", "gemini") and cloud_timeout_mode == "process":
            round1[name] = _invoke_cloud_model_in_subprocess(name, prompt, timeout_s=timeout_s)
        else:
            round1[name] = _invoke_with_timeout(name, m, prompt, timeout_s=timeout_s)

    base_outputs = {}
    for name, r in round1.items():
        base_outputs[name] = r.parsed if r.parsed else {"error": r.error or "parse_failed", "raw": r.raw[:1200]}

    # Round 2: debate/critique (optional)
    round2: Dict[str, ModelResult] = {}
    if rounds >= 2:
        critique_prompt = (
            "You are participating in a multi-analyst debate. You will be shown other models' JSON outputs. "
            "Your task: identify weak reasoning, missed red-flags, and propose an improved ranking.\n\n"
            "Constraints:\n"
            "- Stay grounded in the provided candidate data; do not invent financial statements.\n"
            "- Be extra suspicious of extreme momentum and low liquidity.\n"
            "- Output JSON only, same schema as before.\n\n"
            "Use the candidate rows below as your ONLY source of facts.\n\n"
            f"Candidate rows JSON:\n{candidate_rows_json}\n\n"
            f"Other model outputs JSON: {json.dumps(base_outputs, ensure_ascii=False)}"
        )
        for name, m in models.items():
            print(f"[LLM] Round 2 (debate) -> {name}")
            if name in ("deepseek", "gemini") and cloud_timeout_mode == "process":
                round2[name] = _invoke_cloud_model_in_subprocess(name, critique_prompt, timeout_s=timeout_s)
            else:
                round2[name] = _invoke_with_timeout(name, m, critique_prompt, timeout_s=timeout_s)

    # Consensus synthesis (prefer DeepSeek->Gemini->Ollama)
    consensus: Optional[ModelResult] = None

    # If there's only one model, a separate "chair" step is redundant; reuse the model output.
    if len(models) == 1:
        only_name = next(iter(models.keys()))
        # Prefer debate output if available, else round1.
        if round2 and only_name in round2:
            consensus = round2[only_name]
        else:
            consensus = round1.get(only_name)

        # Providers occasionally ignore the schema. If parse failed or schema invalid, repair.
        if consensus is not None and (consensus.parsed is None or not _looks_like_required_schema(consensus.parsed)):
            m = models[only_name]
            consensus = _repair_to_schema(
                only_name,
                m,
                candidates=candidates,
                content=consensus.raw,
                timeout_s=timeout_s,
                cloud_timeout_mode=cloud_timeout_mode,
            )
    else:
        consensus_model = _choose_consensus_model(models)
        if consensus_model:
            synth_prompt = (
                "You are the chair of the debate. You will be given JSON outputs from multiple models. "
                "Produce the final consensus ranking with the same JSON schema.\n\n"
                "Extra rules:\n"
                "- If data_quality is POOR or red_flags are severe, verdict should be AVOID.\n"
                "- Limit BUY to at most 10 names; the rest should be WATCH/AVOID.\n"
                "- Output JSON only.\n\n"
                f"Round1: {json.dumps(base_outputs, ensure_ascii=False)}\n\n"
                f"Round2: {json.dumps({k:(v.parsed or {'error': v.error, 'raw': v.raw[:1200]}) for k,v in round2.items()}, ensure_ascii=False) if round2 else '{}'}"
            )
            print(f"[LLM] Consensus synthesis -> {consensus_model}")
            if consensus_model in ("deepseek", "gemini") and cloud_timeout_mode == "process":
                consensus = _invoke_cloud_model_in_subprocess(consensus_model, synth_prompt, timeout_s=timeout_s)
            else:
                consensus = _invoke_with_timeout(consensus_model, models[consensus_model], synth_prompt, timeout_s=timeout_s)

            # If the chair didn't follow schema, attempt repair. If still invalid, fall back to another available model.
            if consensus is not None and (consensus.parsed is None or not _looks_like_required_schema(consensus.parsed)):
                consensus = _repair_to_schema(
                    consensus_model,
                    models[consensus_model],
                    candidates=candidates,
                    content=consensus.raw,
                    timeout_s=timeout_s,
                    cloud_timeout_mode=cloud_timeout_mode,
                )

            if consensus is not None and (consensus.parsed is None or not _looks_like_required_schema(consensus.parsed)):
                for fallback in ("gemini", "deepseek"):
                    if fallback != consensus_model and fallback in models:
                        consensus = _repair_to_schema(
                            fallback,
                            models[fallback],
                            candidates=candidates,
                            content=consensus.raw,
                            timeout_s=timeout_s,
                            cloud_timeout_mode=cloud_timeout_mode,
                        )
                        if consensus.parsed is not None and _looks_like_required_schema(consensus.parsed):
                            break

    return {
        "candidates": candidates,
        "enrichment": enrich,
        "round1": {k: {"error": v.error, "parsed": v.parsed, "raw": v.raw} for k, v in round1.items()},
        "round2": {k: {"error": v.error, "parsed": v.parsed, "raw": v.raw} for k, v in round2.items()},
        "consensus": {"model": consensus.model, "error": consensus.error, "parsed": consensus.parsed, "raw": consensus.raw} if consensus else None,
    }


def _load_json_if_exists(path: Path) -> Optional[Any]:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def _load_enrichment_cache(path: Path) -> Dict[str, Dict[str, Any]]:
    raw = _load_json_if_exists(path)
    if isinstance(raw, dict):
        # cache format: {"SYM.TA": {...}, ...}
        return {str(k): v for k, v in raw.items() if isinstance(v, dict)}
    return {}


def _save_enrichment_cache(path: Path, cache: Dict[str, Dict[str, Any]]):
    try:
        _write_json(path, cache)
    except Exception:
        # best-effort; never fail run on cache IO
        pass


def _enrich_symbols(
    symbols: List[str],
    *,
    cache: Dict[str, Dict[str, Any]],
    workers: int,
) -> Dict[str, Dict[str, Any]]:
    """Ensure enrichment for the provided symbols, using and updating cache."""

    out: Dict[str, Dict[str, Any]] = {s: cache[s] for s in symbols if s in cache and isinstance(cache[s], dict)}
    missing = [s for s in symbols if s not in out]
    if not missing:
        return out

    started = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fetch_enrichment, s): s for s in missing}
        for fut in as_completed(futs):
            sym = futs[fut]
            try:
                snap = fut.result()
                out[sym] = snap
                cache[sym] = snap
            except Exception as e:
                snap = {"symbol": sym, "error": str(e)}
                out[sym] = snap
                cache[sym] = snap

    print(f"Enriched {len(missing)} symbols in {round(time.time() - started, 2)}s")
    return out


def _aggregate_from_consensus(consensus_parsed: Dict[str, Any], *, batch_index: int) -> Dict[str, Dict[str, Any]]:
    """Convert a consensus ranking into an aggregation-friendly map.

    Uses conservative rank-based points to reduce cross-batch score scale issues.
    """

    ranked = consensus_parsed.get("ranked") or []
    verdict_weight = {"BUY": 2.0, "WATCH": 1.0, "AVOID": 0.0}

    out: Dict[str, Dict[str, Any]] = {}
    for i, r in enumerate(ranked, start=1):
        sym = r.get("symbol")
        if not sym:
            continue
        v = str(r.get("verdict") or "WATCH").upper()
        w = verdict_weight.get(v, 1.0)
        conf = _safe_float(r.get("confidence"))
        if conf is None:
            conf = 0.5
        dq = str(r.get("data_quality") or "MIXED").upper()
        dq_pen = 1.0
        if dq == "POOR":
            dq_pen = 0.6
        elif dq == "GOOD":
            dq_pen = 1.05

        # Points: verdict dominates; rank provides tie-break. Confidence and data quality modulate.
        base = (w * 100.0) + max(0.0, (len(ranked) - i))
        points = base * (0.5 + 0.5 * conf) * dq_pen

        out[sym] = {
            "symbol": sym,
            "points": points,
            "verdict": v,
            "confidence": conf,
            "data_quality": dq,
            "thesis": r.get("thesis"),
            "red_flags": r.get("red_flags") or [],
            "batch_index": batch_index,
            "rank": i,
        }

    return out


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Run multi-LLM debate to re-rank Israeli market scan outputs.")
    p.add_argument("--scan-json", default=str(Path(__file__).parent / "market_scan_results_full.json"))
    p.add_argument("--top-k", type=int, default=40)
    p.add_argument("--enrich-workers", type=int, default=6)
    p.add_argument(
        "--models",
        default="deepseek,gemini",
        help="Comma-separated list of models to use (subset of: deepseek,gemini,ollama). Default is cloud-only.",
    )
    p.add_argument("--timeout-s", type=int, default=90, help="Per-model timeout in seconds")
    p.add_argument(
        "--cloud-timeout-mode",
        default="thread",
        choices=("thread", "process"),
        help="How to enforce timeouts for cloud models. thread=best-effort (default, stable); process=hard timeout via subprocess.",
    )
    p.add_argument("--out-dir", default=str(Path(__file__).parent / "llm_outputs"))

    # Full-universe batching controls (optional)
    p.add_argument(
        "--mode",
        default="single",
        choices=("single", "batch"),
        help="single: run debate over top-k; batch: screen whole universe in chunks then run a final debate on the top picks",
    )
    p.add_argument("--batch-size", type=int, default=30)
    p.add_argument("--batch-rounds", type=int, default=1, help="Rounds for batch screening (1=independent only, 2=+debate).")
    p.add_argument(
        "--batch-models",
        default="",
        help="Optional override for batch screening models (default: use --models).",
    )
    p.add_argument("--batch-summary-chars", type=int, default=300)
    p.add_argument("--batch-headlines", type=int, default=3)
    p.add_argument("--batch-sleep-s", type=float, default=0.5, help="Sleep between batches to be polite to providers")
    p.add_argument("--max-batches", type=int, default=0, help="For smoke tests: limit batches processed (0=all)")
    p.add_argument(
        "--resume-batch-dir",
        default="",
        help="If set in batch mode, skips batch processing and reruns ONLY the final debate using aggregate.json in this batch_run directory.",
    )
    p.add_argument(
        "--render-only-batch-dir",
        default="",
        help=(
            "Render HTML/PDF reports from an existing batch_run directory WITHOUT running any LLM calls. "
            "Uses aggregate.json (required) + final_debate.json (optional)."
        ),
    )
    p.add_argument(
        "--batch-enrich-mode",
        default="per-batch",
        choices=("per-batch", "prefetch"),
        help=(
            "per-batch: enrich only symbols in the current batch (default; gentler on yfinance). "
            "prefetch: enrich ALL symbols for all batches up-front in one parallel pass."
        ),
    )
    p.add_argument(
        "--prefetch-chunk-size",
        type=int,
        default=120,
        help="When --batch-enrich-mode=prefetch, process symbols in chunks of this size (parallel within each chunk).",
    )
    p.add_argument("--final-top", type=int, default=50, help="How many symbols to take into the final multi-model debate")
    p.add_argument("--final-rounds", type=int, default=2)
    p.add_argument(
        "--final-models",
        default="",
        help="Optional override for final debate models (default: use --models).",
    )
    p.add_argument("--final-summary-chars", type=int, default=600)
    p.add_argument("--final-headlines", type=int, default=5)
    p.add_argument("--enrich-cache", default="", help="Optional path to enrichment cache JSON (defaults under out-dir)")

    # Report output options
    p.add_argument(
        "--report-formats",
        default="md,html,pdf",
        help="Comma-separated list of report outputs to write (subset of: md,html,pdf). Default: md,html,pdf",
    )
    p.add_argument(
        "--report-detail-top",
        type=int,
        default=30,
        help="How many candidates to include in the detailed section of the HTML/PDF report (default: 30)",
    )

    args = p.parse_args(argv)

    scan_path = Path(args.scan_json)
    if not scan_path.exists():
        print(f"Scan JSON not found: {scan_path}")
        return 2

    scan = _read_json(scan_path)

    # --- Render-only mode (no LLM calls) ---
    if args.render_only_batch_dir:
        batch_dir = Path(args.render_only_batch_dir)
        aggregate_path = batch_dir / "aggregate.json"
        if not aggregate_path.exists():
            print(f"Render-only requested but aggregate.json not found: {aggregate_path}")
            return 10

        agg_obj = _load_json_if_exists(aggregate_path) or {}
        agg_list = (agg_obj.get("aggregate") if isinstance(agg_obj, dict) else None) or []
        if not isinstance(agg_list, list) or not agg_list:
            print("Render-only requested but aggregate list is empty")
            return 11

        # Candidates: prefer final_debate.json if present (already contains hydrated + enriched rows)
        final_debate_path = batch_dir / "final_debate.json"
        final_obj = _load_json_if_exists(final_debate_path) or {}
        candidates = (final_obj.get("candidates") if isinstance(final_obj, dict) else None) or []
        if not isinstance(candidates, list) or not candidates:
            # Fallback: hydrate from scan JSON
            universe = _pick_universe(scan)
            by_symbol = {r.get("symbol"): r for r in universe if isinstance(r, dict) and r.get("symbol")}
            top_syms = [r.get("symbol") for r in agg_list[: max(5, int(args.report_detail_top))] if isinstance(r, dict) and r.get("symbol")]
            candidates = [by_symbol[s] for s in top_syms if s in by_symbol]

        fmts = {x.strip().lower() for x in str(args.report_formats).split(",") if x.strip()}
        disclaimer = (
            "Research output only. Not financial advice. Always verify fundamentals, liquidity, and corporate actions. "
            "Kosher screening here is heuristic; treat as preliminary pending manual review."
        )

        ranked_rows = [r for r in agg_list if isinstance(r, dict) and r.get("symbol")]
        detail_top = max(5, int(args.report_detail_top))
        report_candidates = candidates[:detail_top]
        title = f"Israeli Market Report (render-only) ({datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')} UTC)"

        if "html" in fmts:
            html_path = batch_dir / "final_report.html"
            _render_html_report(
                title=title,
                subtitle="Rendered from saved artifacts (no new LLM calls)",
                artifacts_dir=batch_dir,
                universe_rows=len(_pick_universe(scan)),
                scan_path=scan_path,
                ranked_rows=ranked_rows,
                candidates=report_candidates,
                out_path=html_path,
                disclaimer=disclaimer,
            )
            print(f"Wrote: {html_path}")

        if "pdf" in fmts:
            pdf_path = batch_dir / "final_report.pdf"
            pdf_written = _render_pdf_report(
                title=title,
                artifacts_dir=batch_dir,
                universe_rows=len(_pick_universe(scan)),
                scan_path=scan_path,
                ranked_rows=ranked_rows,
                candidates=report_candidates,
                out_path=pdf_path,
                disclaimer=disclaimer,
            )
            if pdf_written:
                print(f"Wrote: {pdf_written}")
            else:
                print("[PDF] Skipped (reportlab not installed)")

        if "md" in fmts:
            # Keep the existing markdown as-is if present; otherwise write a small pointer.
            md_path = batch_dir / "final_report.md"
            if not md_path.exists():
                _write_text(
                    md_path,
                    "\n".join(
                        [
                            f"# {title}",
                            "",
                            f"Scan: `{scan_path}`",
                            f"Artifacts: `{batch_dir}`",
                            "",
                            "(Rendered-only mode; see final_report.html / final_report.pdf)",
                        ]
                    ),
                )
                print(f"Wrote: {md_path}")

        return 0
    # Determine exactly which model backends we need so we don't initialize Ollama unless requested.
    models_csv_base = _parse_model_csv(args.models)
    models_csv_batch = _parse_model_csv(args.batch_models) if args.batch_models else []
    models_csv_final = _parse_model_csv(args.final_models) if args.final_models else []
    allowed = set(models_csv_base + models_csv_batch + models_csv_final)
    if not allowed:
        allowed = {"deepseek", "gemini"}

    all_models = _init_models(allowed)
    all_models = _normalize_models(all_models, args.models)
    if not all_models:
        print("No LLMs available. Set DEEPSEEK_API_KEY and/or GOOGLE_API_KEY, or install/configure Ollama.")
        return 3

    models_batch = _normalize_models(all_models, args.batch_models) if args.batch_models else all_models
    models_final = _normalize_models(all_models, args.final_models) if args.final_models else all_models

    out_dir = Path(args.out_dir)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # Enrichment cache lives under out-dir by default (so batch runs can be resumed)
    enrich_cache_path = Path(args.enrich_cache) if args.enrich_cache else (out_dir / "enrichment_cache.json")
    enrich_cache = _load_enrichment_cache(enrich_cache_path)

    if args.mode == "single":
        candidates = _pick_candidates(scan, top_k=args.top_k)
        symbols = [c["symbol"] for c in candidates]
        print(f"Selected {len(symbols)} candidates for LLM review")

        enrich = _enrich_symbols(symbols, cache=enrich_cache, workers=args.enrich_workers)
        _save_enrichment_cache(enrich_cache_path, enrich_cache)

        payload = _debate_pipeline(
            candidates=candidates,
            enrich=enrich,
            models=models_final,
            timeout_s=args.timeout_s,
            rounds=2,
            summary_chars=args.final_summary_chars,
            headline_count=args.final_headlines,
            cloud_timeout_mode=args.cloud_timeout_mode,
        )

        out_json = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "single",
            "scan_json": str(scan_path),
            "top_k": args.top_k,
            **payload,
        }

        out_path = out_dir / f"llm_debate_{ts}.json"
        _write_json(out_path, out_json)

        consensus = payload.get("consensus") or {}
        consensus_parsed = consensus.get("parsed") if isinstance(consensus, dict) else None

        md_lines = [
            f"# LLM Debate Results ({ts} UTC)",
            "",
            f"Scan: `{scan_path}`",
            f"Candidates reviewed: **{len(candidates)}**",
            "",
        ]
        if consensus_parsed:
            ranked = consensus_parsed.get("ranked") or []
            md_lines.append("## Consensus top picks")
            md_lines.append("")
            for i, r in enumerate(ranked[:15], start=1):
                md_lines.append(
                    f"{i}. **{r.get('symbol')}** — {r.get('verdict')} — score {r.get('score')} — conf {r.get('confidence')}  "
                    f"\n   - thesis: {r.get('thesis')}  "
                    f"\n   - red_flags: {', '.join(r.get('red_flags') or [])}"
                )
            md_lines.append("")
            md_lines.append("## Notes")
            notes_val = consensus_parsed.get("notes")
            if isinstance(notes_val, str):
                notes = [notes_val]
            elif isinstance(notes_val, list):
                notes = notes_val
            else:
                notes = []
            for n in notes:
                md_lines.append(f"- {n}")
        else:
            md_lines.append("## Consensus")
            md_lines.append("")
            md_lines.append("Consensus synthesis failed (model returned non-JSON or error). See JSON output for details.")

        md_path = out_dir / f"llm_debate_{ts}.md"
        _write_text(md_path, "\n".join(md_lines))

        # Optional nice reports
        fmts = {x.strip().lower() for x in str(args.report_formats).split(",") if x.strip()}
        detail_top = max(5, int(args.report_detail_top))
        disclaimer = (
            "Research output only. Not financial advice. Always verify fundamentals, liquidity, and corporate actions. "
            "Kosher screening here is heuristic; treat as preliminary pending manual review."
        )

        consensus_parsed = consensus.get("parsed") if isinstance(consensus, dict) else None
        ranked_rows: List[Dict[str, Any]] = []
        if isinstance(consensus_parsed, dict) and isinstance(consensus_parsed.get("ranked"), list):
            ranked_rows = [r for r in (consensus_parsed.get("ranked") or []) if isinstance(r, dict) and r.get("symbol")]
        else:
            # Fallback: present candidates in current order
            ranked_rows = [
                {
                    "symbol": c.get("symbol"),
                    "verdict": "WATCH",
                    "confidence": None,
                    "thesis": "",
                    "red_flags": [],
                    "avg_points": None,
                }
                for c in candidates
                if isinstance(c, dict) and c.get("symbol")
            ]

        report_candidates = candidates[:detail_top]
        if "html" in fmts:
            html_path = out_dir / f"llm_debate_{ts}.html"
            _render_html_report(
                title=f"Israeli Market Shortlist ({ts} UTC)",
                subtitle="Single-mode multi-LLM screening",
                artifacts_dir=out_dir,
                universe_rows=len(scan.get("results") or []),
                scan_path=scan_path,
                ranked_rows=ranked_rows,
                candidates=report_candidates,
                out_path=html_path,
                disclaimer=disclaimer,
            )
            print(f"Wrote: {html_path}")

        if "pdf" in fmts:
            pdf_path = out_dir / f"llm_debate_{ts}.pdf"
            pdf_written = _render_pdf_report(
                title=f"Israeli Market Shortlist ({ts} UTC)",
                artifacts_dir=out_dir,
                universe_rows=len(scan.get("results") or []),
                scan_path=scan_path,
                ranked_rows=ranked_rows,
                candidates=report_candidates,
                out_path=pdf_path,
                disclaimer=disclaimer,
            )
            if pdf_written:
                print(f"Wrote: {pdf_written}")
            else:
                print("[PDF] Skipped (reportlab not installed)")

        print(f"Wrote: {out_path}")
        print(f"Wrote: {md_path}")
        return 0

    # --- Batch mode ---

    # Resume path: rerun only the final debate from an existing batch_run folder.
    if args.mode == "batch" and args.resume_batch_dir:
        resume_dir = Path(args.resume_batch_dir)
        aggregate_path = resume_dir / "aggregate.json"
        if not aggregate_path.exists():
            print(f"Resume requested but aggregate.json not found: {aggregate_path}")
            return 6

        agg_obj = _load_json_if_exists(aggregate_path) or {}
        agg_list = (agg_obj.get("aggregate") if isinstance(agg_obj, dict) else None) or []
        if not isinstance(agg_list, list) or not agg_list:
            print("Resume requested but aggregate list is empty")
            return 7

        # Load universe for row rehydration
        universe = _pick_universe(scan)
        by_symbol = {r.get("symbol"): r for r in universe if r.get("symbol")}

        final_top = max(10, int(args.final_top))
        top_symbols = [r.get("symbol") for r in agg_list[:final_top] if isinstance(r, dict) and r.get("symbol")]
        final_candidates = [by_symbol[s] for s in top_symbols if s in by_symbol]
        if not final_candidates:
            print("Resume requested but could not map top symbols back to scan rows")
            return 8

        print(f"[Resume] Debating top {len(final_candidates)} candidates from {resume_dir}")
        enrich_final = _enrich_symbols(top_symbols, cache=enrich_cache, workers=args.enrich_workers)
        _save_enrichment_cache(enrich_cache_path, enrich_cache)

        final_payload = _debate_pipeline(
            candidates=final_candidates,
            enrich=enrich_final,
            models=models_final,
            timeout_s=args.timeout_s,
            rounds=max(1, int(args.final_rounds)),
            summary_chars=args.final_summary_chars,
            headline_count=args.final_headlines,
            cloud_timeout_mode=args.cloud_timeout_mode,
        )

        ts2 = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        final_path = resume_dir / f"final_debate_{ts2}.json"
        _write_json(
            final_path,
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "scan_json": str(scan_path),
                "final_top": final_top,
                **final_payload,
            },
        )
        print(f"Wrote: {final_path}")

        consensus = final_payload.get("consensus") or {}
        consensus_parsed = consensus.get("parsed") if isinstance(consensus, dict) else None
        md_lines = [
            f"# Final Debate Resume ({ts2} UTC)",
            "",
            f"Scan: `{scan_path}`",
            f"Resume dir: `{resume_dir}`",
            f"Final debate size: **{len(final_candidates)}**",
            "",
        ]
        if consensus_parsed and isinstance(consensus_parsed, dict):
            ranked = consensus_parsed.get("ranked") or []
            md_lines.append("## Final consensus")
            md_lines.append("")
            for i, r in enumerate(ranked[:20], start=1):
                md_lines.append(
                    f"{i}. **{r.get('symbol')}** — {r.get('verdict')} — score {r.get('score')} — conf {r.get('confidence')}  "
                    f"\n   - thesis: {r.get('thesis')}  "
                    f"\n   - red_flags: {', '.join(r.get('red_flags') or [])}"
                )
            md_lines.append("")
            md_lines.append("## Notes")
            notes_val = consensus_parsed.get("notes")
            notes: List[str]
            if isinstance(notes_val, str):
                notes = [notes_val]
            elif isinstance(notes_val, list):
                notes = [str(x) for x in notes_val]
            else:
                notes = []
            for n in notes:
                md_lines.append(f"- {n}")
        else:
            md_lines.append("## Final consensus")
            md_lines.append("")
            md_lines.append("Consensus output missing or not parseable. See JSON for details.")

        md_path = resume_dir / f"final_report_{ts2}.md"
        _write_text(md_path, "\n".join(md_lines))
        print(f"Wrote: {md_path}")

        # Optional nice reports (resume)
        fmts = {x.strip().lower() for x in str(args.report_formats).split(",") if x.strip()}
        disclaimer = (
            "Research output only. Not financial advice. Always verify fundamentals, liquidity, and corporate actions. "
            "Kosher screening here is heuristic; treat as preliminary pending manual review."
        )

        # Ranking fallback: use aggregate.json ordering (already loaded as agg_list)
        ranked_rows = [r for r in agg_list if isinstance(r, dict) and r.get("symbol")]
        if "html" in fmts:
            html_path = resume_dir / f"final_report_{ts2}.html"
            _render_html_report(
                title=f"Israeli Market Report (resume) ({ts2} UTC)",
                subtitle="Final debate rerun from saved batch_run aggregate.json",
                artifacts_dir=resume_dir,
                universe_rows=len(universe),
                scan_path=scan_path,
                ranked_rows=ranked_rows,
                candidates=final_candidates[: max(5, int(args.report_detail_top))],
                out_path=html_path,
                disclaimer=disclaimer,
            )
            print(f"Wrote: {html_path}")

        if "pdf" in fmts:
            pdf_path = resume_dir / f"final_report_{ts2}.pdf"
            pdf_written = _render_pdf_report(
                title=f"Israeli Market Report (resume) ({ts2} UTC)",
                artifacts_dir=resume_dir,
                universe_rows=len(universe),
                scan_path=scan_path,
                ranked_rows=ranked_rows,
                candidates=final_candidates[: max(5, int(args.report_detail_top))],
                out_path=pdf_path,
                disclaimer=disclaimer,
            )
            if pdf_written:
                print(f"Wrote: {pdf_written}")
            else:
                print("[PDF] Skipped (reportlab not installed)")

        return 0
    universe = _pick_universe(scan)
    if not universe:
        print("No usable rows found in scan JSON")
        return 4

    # Build batches
    batch_size = max(5, int(args.batch_size))
    batches: List[List[Dict[str, Any]]] = [universe[i : i + batch_size] for i in range(0, len(universe), batch_size)]
    if args.max_batches and int(args.max_batches) > 0:
        batches = batches[: int(args.max_batches)]

    print(f"Batch mode: {len(universe)} universe rows -> {len(batches)} batches of ~{batch_size}")

    batch_dir = out_dir / f"batch_run_{ts}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    # Optional: enrich everything up-front in one parallel pass.
    # This can be faster, but it may trigger upstream throttling on some networks.
    if args.batch_enrich_mode == "prefetch":
        all_batch_symbols: List[str] = []
        for b in batches:
            all_batch_symbols.extend([r["symbol"] for r in b if r.get("symbol")])
        # De-dupe while preserving order
        seen = set()
        all_batch_symbols = [s for s in all_batch_symbols if not (s in seen or seen.add(s))]

        chunk_size = max(25, int(args.prefetch_chunk_size))
        print(
            f"\n[Enrich prefetch] Ensuring enrichment for {len(all_batch_symbols)} symbols "
            f"in chunks of {chunk_size} (parallel within chunk, workers={args.enrich_workers})"
        )
        for i in range(0, len(all_batch_symbols), chunk_size):
            chunk = all_batch_symbols[i : i + chunk_size]
            print(f"[Enrich prefetch] Chunk {int(i / chunk_size) + 1}/{int((len(all_batch_symbols) + chunk_size - 1) / chunk_size)} ({len(chunk)} symbols)")
            _ = _enrich_symbols(chunk, cache=enrich_cache, workers=args.enrich_workers)
            _save_enrichment_cache(enrich_cache_path, enrich_cache)
        print("[Enrich prefetch] Done")

    aggregate: Dict[str, Dict[str, Any]] = {}
    for bi, batch in enumerate(batches, start=1):
        batch_symbols = [b["symbol"] for b in batch]
        print(f"\n[Batch {bi}/{len(batches)}] Enriching {len(batch_symbols)} symbols")

        if args.batch_enrich_mode == "prefetch":
            # Prefetched: just read from cache (or fill any rare misses).
            enrich_batch = _enrich_symbols(batch_symbols, cache=enrich_cache, workers=args.enrich_workers)
        else:
            # Default: enrich only what this batch needs.
            enrich_batch = _enrich_symbols(batch_symbols, cache=enrich_cache, workers=args.enrich_workers)
            _save_enrichment_cache(enrich_cache_path, enrich_cache)

        print(f"[Batch {bi}/{len(batches)}] Running LLM screening (rounds={args.batch_rounds})")
        payload = _debate_pipeline(
            candidates=batch,
            enrich=enrich_batch,
            models=models_batch,
            timeout_s=args.timeout_s,
            rounds=max(1, int(args.batch_rounds)),
            summary_chars=args.batch_summary_chars,
            headline_count=args.batch_headlines,
            cloud_timeout_mode=args.cloud_timeout_mode,
        )

        # Persist per-batch payload
        batch_path = batch_dir / f"batch_{bi:03d}.json"
        _write_json(
            batch_path,
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "scan_json": str(scan_path),
                "batch_index": bi,
                "batch_size": len(batch),
                **payload,
            },
        )
        print(f"[Batch {bi}/{len(batches)}] Wrote: {batch_path}")

        consensus = payload.get("consensus") or {}
        consensus_parsed = consensus.get("parsed") if isinstance(consensus, dict) else None
        if consensus_parsed:
            batch_map = _aggregate_from_consensus(consensus_parsed, batch_index=bi)
            for sym, rec in batch_map.items():
                if sym not in aggregate:
                    aggregate[sym] = {
                        "symbol": sym,
                        "total_points": 0.0,
                        "appearances": 0,
                        "best_verdict": rec.get("verdict"),
                        "best_points": rec.get("points"),
                        "examples": [],
                    }

                aggregate[sym]["total_points"] += float(rec.get("points") or 0.0)
                aggregate[sym]["appearances"] += 1
                if float(rec.get("points") or 0.0) > float(aggregate[sym].get("best_points") or 0.0):
                    aggregate[sym]["best_points"] = float(rec.get("points") or 0.0)
                    aggregate[sym]["best_verdict"] = rec.get("verdict")
                if len(aggregate[sym]["examples"]) < 3:
                    aggregate[sym]["examples"].append(
                        {
                            "batch_index": bi,
                            "rank": rec.get("rank"),
                            "verdict": rec.get("verdict"),
                            "confidence": rec.get("confidence"),
                            "data_quality": rec.get("data_quality"),
                            "thesis": rec.get("thesis"),
                            "red_flags": rec.get("red_flags"),
                        }
                    )
        else:
            print(f"[Batch {bi}/{len(batches)}] No consensus JSON returned; skipping aggregation")

        if args.batch_sleep_s and float(args.batch_sleep_s) > 0:
            time.sleep(float(args.batch_sleep_s))

    # Persist aggregate
    agg_list = list(aggregate.values())
    for r in agg_list:
        apps = int(r.get("appearances") or 1)
        r["avg_points"] = float(r.get("total_points") or 0.0) / max(1, apps)

    agg_list_sorted = sorted(agg_list, key=lambda x: float(x.get("avg_points") or 0.0), reverse=True)
    aggregate_path = batch_dir / "aggregate.json"
    _write_json(
        aggregate_path,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scan_json": str(scan_path),
            "mode": "batch",
            "batches_processed": len(batches),
            "universe_count": len(universe),
            "batch_models": list(models_batch.keys()),
            "final_models": list(models_final.keys()),
            "aggregate": agg_list_sorted,
        },
    )
    print(f"\nWrote: {aggregate_path}")

    # Final debate on the top candidates
    final_top = max(10, int(args.final_top))
    top_symbols = [r["symbol"] for r in agg_list_sorted[:final_top] if r.get("symbol")]
    if not top_symbols:
        print("No top symbols to debate; aborting final stage")
        return 5

    # Re-hydrate candidate rows from universe scan
    by_symbol = {r.get("symbol"): r for r in universe if r.get("symbol")}
    final_candidates = [by_symbol[s] for s in top_symbols if s in by_symbol]
    print(f"\n[Final] Debating top {len(final_candidates)} candidates")
    enrich_final = _enrich_symbols(top_symbols, cache=enrich_cache, workers=args.enrich_workers)
    _save_enrichment_cache(enrich_cache_path, enrich_cache)

    final_payload = _debate_pipeline(
        candidates=final_candidates,
        enrich=enrich_final,
        models=models_final,
        timeout_s=args.timeout_s,
        rounds=max(1, int(args.final_rounds)),
        summary_chars=args.final_summary_chars,
        headline_count=args.final_headlines,
        cloud_timeout_mode=args.cloud_timeout_mode,
    )

    final_path = batch_dir / "final_debate.json"
    _write_json(
        final_path,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scan_json": str(scan_path),
            "final_top": final_top,
            **final_payload,
        },
    )
    print(f"Wrote: {final_path}")

    # Final markdown report
    consensus = final_payload.get("consensus") or {}
    consensus_parsed = consensus.get("parsed") if isinstance(consensus, dict) else None
    md_lines = [
        f"# Full-Universe LLM Screening ({ts} UTC)",
        "",
        f"Scan: `{scan_path}`",
        f"Universe rows screened: **{len(universe)}**",
        f"Batches processed: **{len(batches)}** (size ~{batch_size})",
        f"Final debate size: **{len(final_candidates)}**",
        "",
        f"Artifacts: `{batch_dir}`",
        "",
    ]
    md_lines.append("## Aggregate top (pre-debate)")
    md_lines.append("")
    for i, r in enumerate(agg_list_sorted[:20], start=1):
        md_lines.append(
            f"{i}. **{r.get('symbol')}** — avg_points {round(float(r.get('avg_points') or 0.0), 2)} — best {r.get('best_verdict')}"
        )
    md_lines.append("")

    if consensus_parsed:
        ranked = consensus_parsed.get("ranked") or []
        md_lines.append("## Final consensus (debate)")
        md_lines.append("")
        for i, r in enumerate(ranked[:20], start=1):
            md_lines.append(
                f"{i}. **{r.get('symbol')}** — {r.get('verdict')} — score {r.get('score')} — conf {r.get('confidence')}  "
                f"\n   - thesis: {r.get('thesis')}  "
                f"\n   - red_flags: {', '.join(r.get('red_flags') or [])}"
            )
        md_lines.append("")
        md_lines.append("## Notes")
        notes_val = consensus_parsed.get("notes")
        if isinstance(notes_val, str):
            notes = [notes_val]
        elif isinstance(notes_val, list):
            notes = notes_val
        else:
            notes = []
        for n in notes:
            md_lines.append(f"- {n}")
    else:
        md_lines.append("## Final consensus")
        md_lines.append("")
        md_lines.append("Final consensus synthesis failed (model returned non-JSON or error). See final_debate.json for details.")

    md_path = batch_dir / "final_report.md"
    _write_text(md_path, "\n".join(md_lines))
    print(f"Wrote: {md_path}")

    # Optional nice reports (batch mode)
    fmts = {x.strip().lower() for x in str(args.report_formats).split(",") if x.strip()}
    detail_top = max(5, int(args.report_detail_top))
    disclaimer = (
        "Research output only. Not financial advice. Always verify fundamentals, liquidity, and corporate actions. "
        "Kosher screening here is heuristic; treat as preliminary pending manual review."
    )

    # Use aggregate ranking as primary ordering even if the final consensus fails.
    ranked_rows = [r for r in agg_list_sorted if isinstance(r, dict) and r.get("symbol")]
    report_candidates = final_candidates[:detail_top]

    if "html" in fmts:
        html_path = batch_dir / "final_report.html"
        _render_html_report(
            title=f"Israeli Market Report ({ts} UTC)",
            subtitle="Full-universe batch screening + final debate",
            artifacts_dir=batch_dir,
            universe_rows=len(universe),
            scan_path=scan_path,
            ranked_rows=ranked_rows,
            candidates=report_candidates,
            out_path=html_path,
            disclaimer=disclaimer,
        )
        print(f"Wrote: {html_path}")

    if "pdf" in fmts:
        pdf_path = batch_dir / "final_report.pdf"
        pdf_written = _render_pdf_report(
            title=f"Israeli Market Report ({ts} UTC)",
            artifacts_dir=batch_dir,
            universe_rows=len(universe),
            scan_path=scan_path,
            ranked_rows=ranked_rows,
            candidates=report_candidates,
            out_path=pdf_path,
            disclaimer=disclaimer,
        )
        if pdf_written:
            print(f"Wrote: {pdf_written}")
        else:
            print("[PDF] Skipped (reportlab not installed)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
