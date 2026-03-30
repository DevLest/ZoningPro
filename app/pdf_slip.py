"""Generate assessment PDF using ReportLab (Windows-friendly)."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.settings_store import logo_fs_path


def format_peso_plain(n: float) -> str:
    return f"{n:,.2f}"


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
    branding: dict[str, str] | None = None,
) -> None:
    del template_id  # PDF matches official slip; no Excel metadata line.
    b = branding or {}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    tiny = ParagraphStyle(
        "tiny",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
    )
    tiny_b = ParagraphStyle(
        "tiny_b",
        parent=tiny,
        fontName="Helvetica-Bold",
    )
    tiny_center = ParagraphStyle(
        "tiny_c",
        parent=tiny,
        alignment=1,
    )
    tiny_center_b = ParagraphStyle(
        "tiny_cb",
        parent=tiny_b,
        alignment=1,
    )
    tiny_right = ParagraphStyle(
        "tiny_r",
        parent=tiny,
        alignment=2,
        fontName="Courier",
    )
    tiny_right_b = ParagraphStyle(
        "tiny_rb",
        parent=tiny_right,
        fontName="Courier-Bold",
    )

    black = colors.HexColor("#0f172a")
    seal_path = logo_fs_path(b.get("logo_static_relpath", ""))
    header_cells = []
    if seal_path.is_file():
        header_cells.append(Image(str(seal_path), width=0.62 * inch, height=0.62 * inch))
    else:
        header_cells.append(Paragraph("", tiny))
    rep = (b.get("republic_label") or "Republic of the Philippines").replace("&", "&amp;")
    mun = (b.get("municipality_label") or "").replace("&", "&amp;")
    off = (b.get("office_label") or "").replace("&", "&amp;")
    header_cells.append(
        Paragraph(
            f"{rep}<br/>"
            f"<b>{mun}</b><br/>"
            f"<b>{off}</b>",
            ParagraphStyle("hdr", parent=tiny_center, fontSize=8, leading=10, spaceBefore=2),
        )
    )
    header_table = Table([header_cells], colWidths=[0.72 * inch, 5.1 * inch])
    header_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "CENTER")]))

    story = [header_table, Spacer(1, 0.08 * inch)]

    def cell(txt: str, style: ParagraphStyle = tiny) -> Paragraph:
        return Paragraph(txt.replace("&", "&amp;"), style)

    zoning_txt = "0.00 (waived)" if zoning_waived else format_peso_plain(zoning)

    inner = [
        [
            cell("Date:", tiny_b),
            cell(app_date, tiny),
            cell("CTRL. No.:", tiny_b),
            cell(ctrl_no, ParagraphStyle("mono", parent=tiny, fontName="Courier")),
        ],
        [
            cell("<b>Application for Locational Clearance</b>", tiny_center_b),
            "",
            "",
            "",
        ],
        [cell("<b>Computation Slip</b>", ParagraphStyle("cs", parent=tiny_center_b, fontSize=9)), "", "", ""],
        [cell("Applicant:", tiny_b), cell(applicant, tiny), "", ""],
        [cell("Address:", tiny_b), cell(address, tiny), "", ""],
        [cell("Project:", tiny_b), cell(project or "—", tiny), "", ""],
        [cell("Location:", tiny_b), cell(location or "—", tiny), "", ""],
        [cell("Lot Area:", tiny_b), cell(f"{lot_area} SQ. Meters", tiny), "", ""],
        [cell("Project Type:", tiny_b), cell(project_type_label.upper(), tiny_b), "", ""],
        [
            cell("Project Cost:", tiny_b),
            Table(
                [
                    [
                        Paragraph("", tiny),
                        Paragraph("<b>P</b>", ParagraphStyle("pc", parent=tiny_center_b, fontSize=9)),
                        Paragraph(f"<b>{format_peso_plain(project_cost)}</b>", ParagraphStyle("pv", parent=tiny_right_b, fontSize=9)),
                    ]
                ],
                colWidths=[2.4 * inch, 0.35 * inch, 1.1 * inch],
            ),
            "",
            "",
        ],
        [cell("<b>ASSESSMENT</b>", tiny_center_b), "", "", ""],
        [cell("<b>FEES:</b>", tiny_b), "", "", ""],
        [cell("&nbsp;&nbsp;&nbsp;&nbsp;LC Fee:", tiny), "", Paragraph(format_peso_plain(lc_fee), tiny_right), ""],
        [cell("&nbsp;&nbsp;&nbsp;&nbsp;Surcharge:", tiny), "", Paragraph(format_peso_plain(surcharge) if surcharge else "—", tiny_right), ""],
        [
            cell("&nbsp;&nbsp;&nbsp;&nbsp;Zoning Certification:", tiny),
            "",
            Paragraph(zoning_txt, tiny_right),
            "",
        ],
        [
            cell("<b>Total Assessment:</b>", tiny_b),
            "",
            Table(
                [
                    [
                        Paragraph("", tiny),
                        Paragraph("<b>P</b>", ParagraphStyle("t1", parent=tiny_center_b, fontSize=9)),
                        Paragraph(f"<b>{format_peso_plain(total)}</b>", ParagraphStyle("t2", parent=tiny_right_b, fontSize=9)),
                    ]
                ],
                colWidths=[2.4 * inch, 0.35 * inch, 1.1 * inch],
            ),
            "",
        ],
    ]

    sig_left = Paragraph("<b>Assessed:</b><br/><br/><br/>_________________________", tiny)
    sig_name = (b.get("signatory_name") or "").replace("&", "&amp;")
    sig_role = (b.get("signatory_role") or "Zoning Administrator").replace("&", "&amp;")
    sig_right = Paragraph(
        f"<b>Approved:</b><br/><br/><b>{sig_name}</b><br/><i>{sig_role}</i>",
        ParagraphStyle("sig", parent=tiny, alignment=1, fontSize=8),
    )
    inner.append([sig_left, "", sig_right, ""])

    # Merge columns for wide rows: use a simpler 4-col table
    t_inner = Table(
        inner,
        colWidths=[1.1 * inch, 2.5 * inch, 1.0 * inch, 1.1 * inch],
    )
    t_inner.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, black),
                ("SPAN", (0, 1), (3, 1)),
                ("SPAN", (0, 2), (3, 2)),
                ("SPAN", (1, 3), (3, 3)),
                ("SPAN", (1, 4), (3, 4)),
                ("SPAN", (1, 5), (3, 5)),
                ("SPAN", (1, 6), (3, 6)),
                ("SPAN", (1, 7), (3, 7)),
                ("SPAN", (1, 8), (3, 8)),
                ("SPAN", (1, 9), (3, 9)),
                ("SPAN", (0, 10), (3, 10)),
                ("SPAN", (0, 11), (3, 11)),
                ("SPAN", (2, 12), (3, 12)),
                ("SPAN", (2, 13), (3, 13)),
                ("SPAN", (2, 14), (3, 14)),
                ("SPAN", (2, 15), (3, 15)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("SPAN", (0, 16), (1, 16)),
                ("SPAN", (2, 16), (3, 16)),
            ]
        )
    )

    story.append(t_inner)

    footer_note = Paragraph("<b>Note:</b> Please pay at the Municipal Treasurer's Office", tiny)
    if round(surcharge, 2) == 5000:
        sur_footer = Paragraph(
            "ILLEGAL CONSTRUCTION: P 2,500.00<br/>NO LOCATIONAL CLEARANCE: P 2,500.00<br/><br/><b>TOTAL: P 5,000.00</b>",
            ParagraphStyle("sf", parent=tiny, alignment=2, fontSize=7, leading=9),
        )
    elif surcharge and surcharge > 0:
        sur_footer = Paragraph(
            f"<b>Surcharge detail</b><br/><b>TOTAL: P {format_peso_plain(surcharge)}</b>",
            ParagraphStyle("sf2", parent=tiny, alignment=2, fontSize=7, leading=9),
        )
    else:
        sur_footer = Paragraph("", tiny)

    foot = Table([[footer_note, sur_footer]], colWidths=[3.5 * inch, 2.5 * inch])
    foot.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(Spacer(1, 0.06 * inch))
    story.append(foot)

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
    )
    doc.build(story)
