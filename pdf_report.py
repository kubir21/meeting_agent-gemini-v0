"""Generate the client-facing PDF report with fpdf2.

Layout: company name as title, a small details block (date, time, video, duration,
language, report id), an optional overview, then Question N / Answer N pairs.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

from fpdf import FPDF

import config

log = logging.getLogger(__name__)

NAVY = (17, 24, 39)
ACCENT = (79, 70, 229)
LIGHT = (243, 244, 246)
TEXT = (31, 41, 55)
MUTED = (107, 114, 128)

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
        self.set_y(-14)
        self.font("", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 6, self.t(f"Confidential  |  Generated automatically  |  Page {self.page_no()}/{{nb}}"),
                  align="C")


def _title_block(pdf: ReportPDF, company: str) -> None:
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, pdf.w, 46, style="F")
    pdf.set_fill_color(*ACCENT)
    pdf.rect(0, 46, pdf.w, 2, style="F")
    pdf.set_xy(20, 13)
    pdf.set_text_color(255, 255, 255)
    size = 26 if len(company) <= 28 else 20
    pdf.font("B", size)
    pdf.multi_cell(pdf.w - 40, 11, pdf.t(company), align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.font("", 11)
    pdf.set_text_color(199, 210, 254)
    pdf.cell(0, 7, pdf.t("Video Analysis Report"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(56)


def _details_block(pdf: ReportPDF, rows: list[tuple[str, str]]) -> None:
    col_w = (pdf.w - 40) / 2
    pdf.set_fill_color(*LIGHT)
    pdf.set_draw_color(229, 231, 235)
    top = pdf.get_y()
    row_h = 14
    total_h = row_h * ((len(rows) + 1) // 2) + 4
    pdf.rect(20, top, pdf.w - 40, total_h, style="F")
    for i, (label, value) in enumerate(rows):
        x = 24 + (i % 2) * col_w
        y = top + 3 + (i // 2) * row_h
        pdf.set_xy(x, y)
        pdf.font("", 7.5)
        pdf.set_text_color(*MUTED)
        pdf.cell(col_w - 8, 4, pdf.t(label.upper()))
        pdf.set_xy(x, y + 4.5)
        pdf.font("B", 10)
        pdf.set_text_color(*TEXT)
        pdf.cell(col_w - 8, 5, pdf.t(value[:44]))
    pdf.set_y(top + total_h + 8)


def _heading(pdf: ReportPDF, text: str) -> None:
    pdf.font("B", 12)
    pdf.set_text_color(*ACCENT)
    pdf.cell(0, 8, pdf.t(text), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*TEXT)


def _qa_block(pdf: ReportPDF, n: int, item: dict) -> None:
    if pdf.get_y() > pdf.h - 55:
        pdf.add_page()
    w = pdf.w - 40
    pdf.font("B", 9)
    pdf.set_text_color(*ACCENT)
    pdf.cell(0, 6, pdf.t(f"QUESTION {n}"), new_x="LMARGIN", new_y="NEXT")
    pdf.font("B", 11.5)
    pdf.set_text_color(*NAVY)
    pdf.multi_cell(w, 6.5, pdf.t(item["question"]), align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.font("B", 9)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, pdf.t(f"ANSWER {n}"), new_x="LMARGIN", new_y="NEXT")
    pdf.font("", 11)
    pdf.set_text_color(*TEXT)
    pdf.multi_cell(w, 6.5, pdf.t(item["answer"]), align="L", new_x="LMARGIN", new_y="NEXT")
    if item.get("reasoning"):
        pdf.ln(1)
        pdf.font("", 9)
        pdf.set_text_color(*MUTED)
        pdf.multi_cell(w, 5, pdf.t(f"Evidence: {item['reasoning']}"), align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.set_draw_color(229, 231, 235)
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
        pdf.set_text_color(*TEXT)
        pdf.multi_cell(pdf.w - 40, 6, pdf.t(analysis["summary"]), align="L", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(6)
    _heading(pdf, "Key Findings")
    pdf.ln(2)
    for i, item in enumerate(analysis["qa"], 1):
        _qa_block(pdf, i, item)

    out_path = out_dir / f"{report_id}.pdf"
    pdf.output(str(out_path))
    log.info("PDF written to %s", out_path)
    return out_path
