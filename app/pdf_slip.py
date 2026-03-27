"""Generate assessment PDF using ReportLab (Windows-friendly)."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.config import MUNICIPALITY, OFFICE, ZC_ADMIN
from app.fees.registry import get_template


def format_peso(n: float) -> str:
    return f"₱{n:,.2f}"


def build_assessment_pdf(
    *,
    out_path: Path,
    ctrl_no: str,
    app_date: str,
    applicant: str,
    address: str,
    project: str,
    location: str,
    lot_area: str,
    project_type_label: str,
    project_cost: float,
    template_id: str,
    lc_fee: float,
    surcharge: float,
    zoning: float,
    total: float,
    zoning_waived: bool = False,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    meta = get_template(template_id)
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "t",
        parent=styles["Normal"],
        fontSize=9,
        alignment=1,
        spaceAfter=4,
    )
    body = ParagraphStyle(
        "b",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
    )

    story = []
    story.append(Paragraph("Republic of the Philippines", title))
    story.append(Paragraph(MUNICIPALITY, title))
    story.append(Paragraph(OFFICE, title))
    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph("<b>APPLICATION FOR LOCATIONAL CLEARANCE</b> — Computation Slip", title))
    story.append(Paragraph(f"<b>Excel template:</b> {meta.sheet_name}", body))
    story.append(Spacer(1, 0.12 * inch))

    info_data = [
        ["Date:", app_date, "CTRL. No.:", ctrl_no],
        ["Applicant:", applicant, "", ""],
        ["Address:", address, "", ""],
        ["Project:", project, "", ""],
        ["Location:", location, "", ""],
        ["Lot Area:", lot_area, "SQ. Meters", ""],
        ["Project Type:", project_type_label, "", ""],
        ["Project Cost:", format_peso(project_cost), "", ""],
    ]
    t1 = Table([[Paragraph(str(a), body) for a in row[:2]] for row in info_data], colWidths=[1.1 * inch, 5 * inch])
    t1.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(t1)
    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph("<b>ASSESSMENT</b>", body))
    zoning_label = f"{format_peso(zoning)} (waived)" if zoning_waived else format_peso(zoning)
    fee_rows = [
        ["FEES:", ""],
        ["LC Fee:", format_peso(lc_fee)],
        ["Surcharge:", format_peso(surcharge)],
        ["Zoning Certification:", zoning_label],
        ["Total Assessment:", format_peso(total)],
    ]
    t2 = Table([[Paragraph(a, body), Paragraph(b, body)] for a, b in fee_rows], colWidths=[2 * inch, 2.5 * inch])
    t2.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(t2)
    story.append(Spacer(1, 0.25 * inch))
    story.append(Paragraph(f"Assessed: _________________ &nbsp; Approved: _________________", body))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(f"<b>{ZC_ADMIN}</b><br/>Zoning Administrator", title))
    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph("Please pay at the Municipal Treasurer's Office", body))

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
    )
    doc.build(story)
