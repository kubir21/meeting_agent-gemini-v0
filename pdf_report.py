"""Generate the client-facing PDF report with fpdf2.

Layout: charcoal title band with amber rule, details block, overview, then numbered
findings (topic, question, answer, evidence). Colours match the web app.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

from fpdf import FPDF

import config

log = logging.getLogger(__name__)

# Palette matches the web app (light theme).
CHARCOAL = (30, 41, 59)     # #1E293B
OFFWHITE = (248, 250, 252)  # #F8FAFC
AMBER = (250, 204, 21)      # #FACC15
TEAL = (13, 148, 136)       # #0D9488
MUTED = (100, 116, 139)     # #64748B
LINE = (226, 232, 240)      # #E2E8F0
SLATE_LIGHT = (203, 213, 225)

_LATIN1_MAP = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-", "\u2026": "...", "\u00a0": " ", "\u20b9": "Rs.",
})


def _time_label(dt: datetime) -> str:
    off = dt.strftime("%z")
    off = f"UTC{off[:3]}:{off[3:]}" if off else ""
    return f"{dt.strftime('%I:%M %p')} ({off})" if off else dt.strftime("%I:%M %p")


def clean_company(name: str) -> str:
    """Strip an 'Implied:' prefix and fall back to a generic title."""
    name = re.sub(r"^\s*implied\s*:\s*", "", name or "", flags=re.IGNORECASE).strip()
    if not name or name.lower().startswith("not mentioned"):
        return "Video Analysis Report"
    return name


class ReportPDF(FPDF):
    def __init__(self) -> None:
        super().__init__(format="A4")
        self.family = "Helvetica"
        self.unicode = False
        self._setup_fonts()
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(20, 20, 20)
        self.alias_nb_pages()

    def _setup_fonts(self) -> None:
        """Bundled Noto -> Windows Arial -> core Helvetica (Latin-1 sanitised)."""
        candidates = [
            (config.FONTS_DIR / "NotoSans-Regular.ttf", config.FONTS_DIR / "NotoSans-Bold.ttf",
             [(config.FONTS_DIR / "NotoSansDevanagari-Regular.ttf",
               config.FONTS_DIR / "NotoSansDevanagari-Bold.ttf")]),
            (Path(r"C:\Windows\Fonts\arial.ttf"), Path(r"C:\Windows\Fonts\arialbd.ttf"),
             [(Path(r"C:\Windows\Fonts\ARIALUNI.ttf"), None)]),
        ]
        for regular, bold, fallbacks in candidates:
            if not regular.exists():
                continue
            try:
                self.add_font("Main", "", str(regular))
                self.add_font("Main", "B", str(bold if bold and bold.exists() else regular))
                names = []
                for i, (fb_reg, fb_bold) in enumerate(fallbacks):
                    if fb_reg.exists():
                        name = f"Fallback{i}"
                        self.add_font(name, "", str(fb_reg))
                        self.add_font(name, "B", str(fb_bold if fb_bold and fb_bold.exists() else fb_reg))
                        names.append(name)
                if names:
                    self.set_fallback_fonts(names, exact_match=False)
                self.family, self.unicode = "Main", True
                try:
                    self.set_text_shaping(True)
                except Exception as exc:
                    log.warning("Text shaping unavailable (%s).", exc)
                return
            except Exception as exc:
                log.warning("Failed to load font %s: %s", regular, exc)
        log.warning("No Unicode font found; using Helvetica.")

    def t(self, text: str) -> str:
        text = str(text).replace("\r\n", "\n").replace("\t", "    ")
        if self.unicode:
            return text
        return text.translate(_LATIN1_MAP).encode("latin-1", "replace").decode("latin-1")

    def font(self, style: str = "", size: float = 10.5) -> None:
        self.set_font(self.family, style, size)

    def footer(self) -> None:
        self.set_draw_color(*LINE)
        self.line(20, self.h - 16, self.w - 20, self.h - 16)
        self.set_y(-13)
        self.font("", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 6, self.t("Video Insights  |  Confidential"), align="L")
        self.set_x(20)
        self.cell(0, 6, self.t(f"Page {self.page_no()} of {{nb}}"), align="R")


def _title_block(pdf: ReportPDF, company: str) -> None:
    pdf.set_fill_color(*CHARCOAL)
    pdf.rect(0, 0, pdf.w, 44, style="F")
    pdf.set_fill_color(*AMBER)
    pdf.rect(0, 44, pdf.w, 1.6, style="F")
    pdf.set_xy(20, 12)
    pdf.font("B", 8.5)
    pdf.set_text_color(*AMBER)
    pdf.cell(0, 5, pdf.t("VIDEO ANALYSIS REPORT"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(20)
    pdf.set_text_color(*OFFWHITE)
    pdf.font("B", 24 if len(company) <= 30 else 18)
    pdf.multi_cell(pdf.w - 40, 10, pdf.t(company), align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(56)


def _details_block(pdf: ReportPDF, rows: list[tuple[str, str]]) -> None:
    col_w = (pdf.w - 40) / 2
    top = pdf.get_y()
    row_h = 14
    total_h = row_h * ((len(rows) + 1) // 2) + 4
    pdf.set_fill_color(*OFFWHITE)
    pdf.set_draw_color(*LINE)
    pdf.rect(20, top, pdf.w - 40, total_h, style="DF")
    for i, (label, value) in enumerate(rows):
        x = 24 + (i % 2) * col_w
        y = top + 3 + (i // 2) * row_h
        pdf.set_xy(x, y)
        pdf.font("", 7.5)
        pdf.set_text_color(*MUTED)
        pdf.cell(col_w - 8, 4, pdf.t(label.upper()))
        pdf.set_xy(x, y + 4.5)
        pdf.font("B", 10)
        pdf.set_text_color(*CHARCOAL)
        pdf.cell(col_w - 8, 5, pdf.t(value[:44]))
    pdf.set_y(top + total_h + 10)


def _heading(pdf: ReportPDF, text: str) -> None:
    pdf.font("B", 13)
    pdf.set_text_color(*CHARCOAL)
    pdf.cell(0, 7, pdf.t(text), new_x="LMARGIN", new_y="NEXT")
    y = pdf.get_y() + 0.5
    pdf.set_fill_color(*AMBER)
    pdf.rect(20, y, 14, 1, style="F")
    pdf.set_y(y + 5)


def _qa_block(pdf: ReportPDF, n: int, item: dict) -> None:
    if pdf.get_y() > pdf.h - 70:
        pdf.add_page()
    w = pdf.w - 40
    topic, sep, ask = item["question"].partition(": ")
    if not sep:
        topic, ask = item["question"], ""
    pdf.font("B", 12)
    pdf.set_text_color(*TEAL)
    pdf.cell(9, 7, pdf.t(f"{n}."))
    pdf.set_text_color(*CHARCOAL)
    pdf.multi_cell(w - 9, 7, pdf.t(topic), align="L", new_x="LMARGIN", new_y="NEXT")
    if ask:
        pdf.font("", 9.5)
        pdf.set_text_color(*MUTED)
        pdf.set_x(29)
        pdf.multi_cell(w - 9, 5.2, pdf.t(ask), align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2.5)
    pdf.font("", 10.5)
    pdf.set_text_color(*CHARCOAL)
    pdf.set_x(29)
    pdf.multi_cell(w - 9, 6, pdf.t(item["answer"]), align="L", new_x="LMARGIN", new_y="NEXT")
    if item.get("reasoning"):
        pdf.ln(1.5)
        y0 = pdf.get_y()
        pdf.font("", 8.5)
        pdf.set_text_color(*MUTED)
        pdf.set_x(32)
        pdf.multi_cell(w - 12, 4.8, pdf.t(f"Evidence: {item['reasoning']}"), align="L",
                       new_x="LMARGIN", new_y="NEXT")
        pdf.set_fill_color(*SLATE_LIGHT)
        pdf.rect(29, y0, 0.6, pdf.get_y() - y0, style="F")
    pdf.ln(4)
    pdf.set_draw_color(*LINE)
    pdf.line(20, pdf.get_y(), pdf.w - 20, pdf.get_y())
    pdf.ln(6)


def build_pdf(analysis: dict, source_name: str, report_id: str, generated_at: datetime,
              out_dir: Path | None = None) -> Path:
    """Render the report to temp/<report_id>.pdf and return the path."""
    out_dir = out_dir or config.TEMP_DIR
    out_dir.mkdir(exist_ok=True)
    company = clean_company(analysis.get("company_name", ""))

    pdf = ReportPDF()
    pdf.add_page()
    _title_block(pdf, company)
    _details_block(pdf, [
        ("Report date", generated_at.strftime("%d %B %Y")),
        ("Report time", _time_label(generated_at)),
        ("Source video", source_name),
        ("Video duration", analysis.get("video_duration", "Not available")),
        ("Language", analysis.get("language", "Not available")),
        ("Report ID", report_id),
    ])
    if analysis.get("summary"):
        _heading(pdf, "Overview")
        pdf.font("", 10.5)
        pdf.set_text_color(*CHARCOAL)
        pdf.multi_cell(pdf.w - 40, 6, pdf.t(analysis["summary"]), align="L", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(6)
    _heading(pdf, "Key Findings")
    for i, item in enumerate(analysis["qa"], 1):
        _qa_block(pdf, i, item)

    out_path = out_dir / f"{report_id}.pdf"
    pdf.output(str(out_path))
    log.info("PDF written to %s", out_path)
    return out_path
