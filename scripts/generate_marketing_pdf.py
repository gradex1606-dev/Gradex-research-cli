"""Generate docs/gradex-x-marketing-brief.pdf from the markdown brief."""

from __future__ import annotations

import re
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parent.parent
MD_PATH = ROOT / "docs" / "gradex-x-marketing-brief.md"
PDF_PATH = ROOT / "docs" / "gradex-x-marketing-brief.pdf"


def _ascii(text: str) -> str:
    """Keep PDF output compatible with core Helvetica font."""
    replacements = {
        "\u2014": "-",
        "\u2013": "-",
        "\u2192": "->",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2026": "...",
        "\u2713": "[x]",
        "\u2610": "[ ]",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", errors="replace").decode("latin-1")


class BriefPDF(FPDF):
  def header(self) -> None:
    if self.page_no() == 1:
      return
    self.set_font("Helvetica", "I", 8)
    self.set_text_color(100, 100, 100)
    self.cell(0, 6, "GradeX Marketing Brief", align="R", new_x="LMARGIN", new_y="NEXT")
    self.set_text_color(0, 0, 0)
    self.ln(1)

  def footer(self) -> None:
    self.set_y(-12)
    self.set_font("Helvetica", "I", 8)
    self.set_text_color(100, 100, 100)
    self.cell(0, 8, f"Page {self.page_no()}", align="C")
    self.set_text_color(0, 0, 0)


def _write_wrapped(pdf: BriefPDF, text: str, *, bold: bool = False, size: int = 10) -> None:
  style = "B" if bold else ""
  pdf.set_font("Helvetica", style=style, size=size)
  pdf.set_x(pdf.l_margin)
  safe = _ascii(text).replace("\t", " ")
  safe = re.sub(r"(https?://\S+)", lambda m: m.group(1).replace("/", "/ "), safe)
  pdf.multi_cell(pdf.epw, 5.5, safe)


def build_pdf(md_text: str) -> BriefPDF:
  pdf = BriefPDF()
  pdf.set_margins(18, 18, 18)
  pdf.set_auto_page_break(auto=True, margin=18)
  pdf.add_page()

  in_code = False
  code_lines: list[str] = []

  for lineno, raw in enumerate(md_text.splitlines(), start=1):
    line = raw.rstrip()

    if line.strip() in {"---", "***", "___"}:
      pdf.ln(2)
      continue

    if pdf.get_y() > pdf.h - pdf.b_margin - 10:
      pdf.add_page()

    if line.strip().startswith("```"):
      if in_code:
        pdf.set_font("Courier", size=9)
        pdf.set_fill_color(245, 245, 245)
        block = "\n".join(code_lines)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.epw, 4.8, _ascii(block), fill=True)
        pdf.ln(2)
        code_lines = []
        in_code = False
      else:
        in_code = True
      continue

    if in_code:
      code_lines.append(line)
      continue

    if not line.strip():
      pdf.ln(2)
      continue

    if line.startswith("# "):
      pdf.ln(2)
      _write_wrapped(pdf, line[2:].strip(), bold=True, size=18)
      pdf.ln(2)
      continue

    if line.startswith("## "):
      pdf.ln(3)
      _write_wrapped(pdf, line[3:].strip(), bold=True, size=13)
      pdf.ln(1)
      continue

    if line.startswith("### "):
      pdf.ln(2)
      _write_wrapped(pdf, line[4:].strip(), bold=True, size=11)
      pdf.ln(1)
      continue

    if line.startswith("|") and "|" in line[1:]:
      if re.match(r"^\|[\s\-:|]+\|$", line.strip()):
        continue
      cells = [c.strip() for c in line.strip("|").split("|")]
      row = "  |  ".join(cells)
      _write_wrapped(pdf, row, size=9)
      continue

    if line.startswith("- [ ]") or line.startswith("- [x]"):
      _write_wrapped(pdf, f"  {line[2:].strip()}", size=10)
      continue

    if line.startswith("- "):
      _write_wrapped(pdf, f"  - {line[2:].strip()}", size=10)
      continue

    if re.match(r"^\d+\.\s", line):
      _write_wrapped(pdf, f"  {line.strip()}", size=10)
      continue

    if line.startswith(">"):
      pdf.set_text_color(60, 60, 60)
      _write_wrapped(pdf, line.lstrip("> ").strip(), size=10)
      pdf.set_text_color(0, 0, 0)
      continue

    # Strip light markdown emphasis for body text
    clean = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
    clean = re.sub(r"\*(.+?)\*", r"\1", clean)
    clean = re.sub(r"`(.+?)`", r"\1", clean)
    try:
      _write_wrapped(pdf, clean, size=10)
    except Exception as exc:
      raise RuntimeError(f"PDF render failed at line {lineno}: {clean!r}") from exc

  return pdf


def main() -> None:
  if not MD_PATH.is_file():
    raise SystemExit(f"Missing source file: {MD_PATH}")

  pdf = build_pdf(MD_PATH.read_text(encoding="utf-8"))
  PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
  pdf.output(str(PDF_PATH))
  print(f"Wrote {PDF_PATH}")


if __name__ == "__main__":
  main()
