# SPDX-License-Identifier: GPL-3.0-or-later
"""
scripts/generate_chessboard_pdf.py — generate assets/chessboard_9x6_25mm.pdf.

Run once to (re)generate the printable chessboard PDF:

    uv run python scripts/generate_chessboard_pdf.py

Requires: reportlab (already in pyproject.toml dependencies).
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def generate_chessboard_pdf(output_path: Path) -> None:
    """
    Generate a 9×6 inner-corner chessboard PDF on A4 paper.

    The board has 10 columns × 7 rows of alternating black/white squares so
    that the inner corner grid is 9×6.  Each square is 25 mm × 25 mm.
    """
    cols = 10           # number of squares along x (→ 9 inner corners)
    rows = 7            # number of squares along y (→ 6 inner corners)
    sq = 25.0           # square size in mm

    board_w_mm = cols * sq   # 250 mm
    board_h_mm = rows * sq   # 175 mm

    page_w, page_h = A4          # 595.27 × 841.89 pt  (≈ 210 × 297 mm)

    # Centre the board on the page.
    margin_x = (page_w - board_w_mm * mm) / 2
    margin_y = (page_h - board_h_mm * mm) / 2 + 20 * mm  # slight upward shift for label

    output_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output_path), pagesize=A4)

    # --- Draw border -----------------------------------------------------------
    border_pad = 2 * mm
    c.setLineWidth(0.5)
    c.rect(
        margin_x - border_pad,
        margin_y - border_pad,
        board_w_mm * mm + 2 * border_pad,
        board_h_mm * mm + 2 * border_pad,
        stroke=1, fill=0,
    )

    # --- Draw squares ----------------------------------------------------------
    for row in range(rows):
        for col in range(cols):
            # Black square when (row + col) is even — matches OpenCV convention
            # where the top-left square is black.
            if (row + col) % 2 == 0:
                x = margin_x + col * sq * mm
                # ReportLab Y axis: bottom = 0. Row 0 = top of board.
                y = margin_y + (rows - 1 - row) * sq * mm
                c.setFillColorRGB(0, 0, 0)
                c.rect(x, y, sq * mm, sq * mm, stroke=0, fill=1)

    # --- Label below the board ------------------------------------------------
    label_y = margin_y - 10 * mm
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(page_w / 2, label_y, "9×6 / 25 mm — Phase 2.5 Lens Calibration")

    # --- Printing instructions below the label --------------------------------
    instructions = [
        "Print at 100% scale (no 'fit to page'). Confirm with a ruler that one square = 25 mm.",
        "Mount on a rigid backing (clipboard / cardboard). Keep flat — do not curve.",
    ]
    c.setFont("Helvetica", 9)
    for i, line in enumerate(instructions):
        c.drawCentredString(page_w / 2, label_y - (i + 1) * 5 * mm, line)

    c.save()
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    here = Path(__file__).resolve().parent.parent
    output = here / "assets" / "chessboard_9x6_25mm.pdf"
    generate_chessboard_pdf(output)
