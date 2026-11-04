"""Generate a professional, Unicode-safe PDF report with fpdf2."""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

from fpdf import FPDF
from fpdf.fonts import FontFace

import config

log = logging.getLogger(__name__)

PRIMARY = (30, 58, 138)      # indigo-900
ACCENT = (79, 70, 229)       # indigo-600
LIGHT = (238, 242, 255)      # indigo-50
TEXT = (31, 41, 55)          # gray-800
MUTED = (107, 114, 128)      # gray-500

_SPEAKER_RE = re.compile(r"^\s*([^:\n]{1,40}?):\s+(.*)$", re.DOTALL)

_LATIN1_MAP = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-", "\u2026": "...", "\u00a0": " ", "\u20b9": "Rs.",
})


class ReportPDF(FPDF):
    def __init__(self) -> None:
        super().__init__(format="A4")
        self.font_family_name = "Helvetica"
        self.unicode = False
        self._setup_fonts()
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(18, 18, 18)
        self.alias_nb_pages()

    # --- fonts -------------------------------------------------------------
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
                fallback_names = []
                for i, (fb_reg, fb_bold) in enumerate(fallbacks):
                    if fb_reg.exists():
                        name = f"Fallback{i}"
                        self.add_font(name, "", str(fb_reg))
                        self.add_font(name, "B", str(fb_bold if fb_bold and fb_bold.exists() else fb_reg))
                        fallback_names.append(name)
                if fallback_names:
                    self.set_fallback_fonts(fallback_names, exact_match=False)
                self.font_family_name = "Main"
                self.unicode = True
                try:
                    self.set_text_shaping(True)  # proper Devanagari conjuncts (needs uharfbuzz)
                except Exception as exc:
                    log.warning("Text shaping unavailable (%s); continuing without it.", exc)
                return
            except Exception as exc:
                log.warning("Failed to load font %s: %s", regular, exc)
        log.warning("No Unicode font found; falling back to Helvetica (non-Latin text will be replaced).")

    def t(self, text: str) -> str:
        """Make text safe for the active font."""
        text = str(text).replace("\r\n", "\n").replace("\t", "    ")
        if self.unicode:
            return text
        return text.translate(_LATIN1_MAP).encode("latin-1", "replace").decode("latin-1")

    def font(self, style: str = "", size: float = 10.5) -> None:
        self.set_font(self.font_family_name, style, size)

    # --- page furniture ----------------------------------------------------
    def footer(self) -> None:
        self.set_y(-12)
        self.font("", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 6, self.t(f"Automated Video Analysis Report  |  Page {self.page_no()}/{{nb}}"), align="C")

    def section_title(self, title: str) -> None:
        if self.get_y() > self.h - 50:
            self.add_page()
        self.ln(4)
        self.font("B", 14)
        self.set_text_color(*PRIMARY)
        self.cell(0, 9, self.t(title), new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*ACCENT)
        self.set_line_width(0.6)
        self.line(self.l_margin, self.get_y(), self.l_margin + 30, self.get_y())
        self.ln(4)
        self.set_text_color(*TEXT)


def _render_header(pdf: ReportPDF, source_name: str, model: str) -> None:
    pdf.set_fill_color(*PRIMARY)
    pdf.rect(0, 0, pdf.w, 38, style="F")
    pdf.set_xy(18, 10)
    pdf.font("B", 20)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 10, pdf.t("Automated Video Analysis Report"), new_x="LMARGIN", new_y="NEXT")
    pdf.font("", 9.5)
    pdf.set_text_color(199, 210, 254)
    pdf.cell(0, 6, pdf.t(f"Source video: {source_name}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, pdf.t(f"Generated: {datetime.now():%d %b %Y, %H:%M}   |   Model: {model}"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(46)
    pdf.set_text_color(*TEXT)


def _render_qa(pdf: ReportPDF, qa: list[dict]) -> None:
    pdf.section_title("Contextual Q&A Analysis")
    pdf.font("", 10)
    pdf.set_fill_color(255, 255, 255)   # non-striped rows stay white
    pdf.set_draw_color(209, 213, 219)
    pdf.set_line_width(0.2)
    heading = FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=ACCENT)
    with pdf.table(
        col_widths=(10, 62, 102),
        text_align=("CENTER", "LEFT", "LEFT"),
        headings_style=heading,
        cell_fill_color=LIGHT,
        cell_fill_mode="ROWS",
        line_height=6,
        padding=2.5,
        borders_layout="HORIZONTAL_LINES",
    ) as table:
        row = table.row()
        for h in ("#", "Question", "Answer"):
            row.cell(pdf.t(h))
        for i, item in enumerate(qa, 1):
            row = table.row()
            row.cell(str(i))
            row.cell(pdf.t(item["question"]), style=FontFace(emphasis="BOLD"))
            answer = item["answer"]
            if item.get("reasoning"):
                answer += f"\n\nEvidence: {item['reasoning']}"
            row.cell(pdf.t(answer))


def _render_transcript(pdf: ReportPDF, transcript: str) -> None:
    pdf.section_title("Extracted Transcript")
    label_w = 34
    usable = pdf.w - pdf.l_margin - pdf.r_margin
    for raw in transcript.split("\n"):
        line = raw.strip()
        if not line:
            pdf.ln(2)
            continue
        if pdf.get_y() > pdf.h - 30:
            pdf.add_page()
        m = _SPEAKER_RE.match(line)
        y0 = pdf.get_y()
        if m:
            label, rest = m.group(1).strip() + ":", m.group(2).strip()
            pdf.font("B", 10)
            pdf.set_text_color(*ACCENT)
            if pdf.get_string_width(pdf.t(label)) < label_w - 2:
                pdf.set_x(pdf.l_margin)
                pdf.cell(label_w, 6, pdf.t(label))
                pdf.font("", 10.5)
                pdf.set_text_color(*TEXT)
                pdf.set_xy(pdf.l_margin + label_w, y0)
                pdf.multi_cell(usable - label_w, 6, pdf.t(rest), align="L", new_x="LMARGIN", new_y="NEXT")
            else:
                pdf.multi_cell(usable, 6, pdf.t(label), align="L", new_x="LMARGIN", new_y="NEXT")
                pdf.font("", 10.5)
                pdf.set_text_color(*TEXT)
                pdf.multi_cell(usable, 6, pdf.t(rest), align="L", new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.font("", 10.5)
            pdf.set_text_color(*TEXT)
            pdf.multi_cell(usable, 6, pdf.t(line), align="L", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1.2)


def build_pdf(analysis: dict, source_name: str, out_dir: Path | None = None) -> Path:
    """Render the analysis to `temp/report_<uuid>.pdf` and return the path."""
    out_dir = out_dir or config.TEMP_DIR
    out_dir.mkdir(exist_ok=True)
    pdf = ReportPDF()
    pdf.add_page()
    _render_header(pdf, source_name, analysis.get("model", config.GEMINI_MODEL))
    _render_qa(pdf, analysis["qa"])
    _render_transcript(pdf, analysis["transcript"])
    out_path = out_dir / f"report_{uuid.uuid4().hex}.pdf"
    pdf.output(str(out_path))
    log.info("PDF written to %s", out_path)
    return out_path
