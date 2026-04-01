# app/utils/pdf_generators/quotation_pdf.py
# Production-grade branded GST quotation PDF generator

import os
from decimal import Decimal
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.billing.quotation_models import Quotation, QuotationItem
from app.core.exceptions import AppException
from app.constants.error_codes import ErrorCode
from app.core.config import (
    COMPANY_NAME,
    COMPANY_GSTIN,
    COMPANY_ADDRESS_LINE1,
    COMPANY_ADDRESS_LINE2,
    COMPANY_PHONE,
    COMPANY_EMAIL,
    UPLOAD_BASE_DIR,
)

QUOTATION_OUTPUT_DIR = os.path.join(UPLOAD_BASE_DIR, "quotations")

# ─────────────────────────────────────────────────────────────────
# COLOR PALETTE
# ─────────────────────────────────────────────────────────────────
COLOR_PRIMARY   = colors.HexColor("#1a1a2e")
COLOR_SECONDARY = colors.HexColor("#16213e")
COLOR_ACCENT    = colors.HexColor("#0f3460")
COLOR_LIGHT     = colors.HexColor("#f5f5f5")
COLOR_BORDER    = colors.HexColor("#cccccc")
COLOR_WHITE     = colors.white
COLOR_TEXT      = colors.HexColor("#333333")
COLOR_MUTED     = colors.HexColor("#777777")


def _styles():
    return {
        "company_name": ParagraphStyle(
            "company_name",
            fontSize=18, fontName="Helvetica-Bold",
            textColor=COLOR_WHITE, alignment=TA_LEFT, spaceAfter=2,
        ),
        "company_sub": ParagraphStyle(
            "company_sub",
            fontSize=8, fontName="Helvetica",
            textColor=colors.HexColor("#cccccc"), alignment=TA_LEFT, leading=12,
        ),
        "doc_label": ParagraphStyle(
            "doc_label",
            fontSize=22, fontName="Helvetica-Bold",
            textColor=COLOR_WHITE, alignment=TA_RIGHT,
        ),
        "doc_meta": ParagraphStyle(
            "doc_meta",
            fontSize=8, fontName="Helvetica",
            textColor=colors.HexColor("#cccccc"), alignment=TA_RIGHT, leading=12,
        ),
        "section_header": ParagraphStyle(
            "section_header",
            fontSize=8, fontName="Helvetica-Bold",
            textColor=COLOR_ACCENT, spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "body",
            fontSize=9, fontName="Helvetica",
            textColor=COLOR_TEXT, leading=13,
        ),
        "bold": ParagraphStyle(
            "bold",
            fontSize=9, fontName="Helvetica-Bold",
            textColor=COLOR_TEXT,
        ),
        "grand_total": ParagraphStyle(
            "grand_total",
            fontSize=12, fontName="Helvetica-Bold",
            textColor=COLOR_WHITE, alignment=TA_RIGHT,
        ),
        "footer": ParagraphStyle(
            "footer",
            fontSize=8, fontName="Helvetica",
            textColor=COLOR_MUTED, alignment=TA_CENTER,
        ),
    }


async def generate_quotation_pdf(db: AsyncSession, quotation_id: int) -> str:
    """
    Generate a branded GST-compliant quotation PDF.
    Returns the file path to the saved PDF.
    """
    # ── Fetch quotation with all required relationships ────────────
    result = await db.execute(
        select(Quotation)
        .options(
            selectinload(Quotation.items).selectinload(QuotationItem.product),
            selectinload(Quotation.customer),
        )
        .where(
            Quotation.id == quotation_id,
            Quotation.is_deleted.is_(False),
        )
    )
    quotation = result.scalar_one_or_none()
    if not quotation:
        raise AppException(404, "Quotation not found", ErrorCode.QUOTATION_NOT_FOUND)

    customer = quotation.customer
    items = [i for i in quotation.items if not i.is_deleted]

    # ── Ensure output directory exists ────────────────────────────
    os.makedirs(QUOTATION_OUTPUT_DIR, exist_ok=True)
    file_name = f"Quotation_{quotation.quotation_number}.pdf"
    file_path = os.path.join(QUOTATION_OUTPUT_DIR, file_name)

    # ── Build PDF ──────────────────────────────────────────────────
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=10 * mm,
        bottomMargin=15 * mm,
    )

    S = _styles()
    story = []
    page_width = A4[0] - 30 * mm

    # ══════════════════════════════════════════════════════════════
    # HEADER BANNER
    # ══════════════════════════════════════════════════════════════
    valid_until_str = quotation.valid_until.strftime("%d %b %Y") if quotation.valid_until else "N/A"

    header_data = [[
        [
            Paragraph(COMPANY_NAME, S["company_name"]),
            Paragraph(
                f"{COMPANY_ADDRESS_LINE1}<br/>{COMPANY_ADDRESS_LINE2}<br/>"
                f"Phone: {COMPANY_PHONE} | Email: {COMPANY_EMAIL}<br/>"
                f"GSTIN: {COMPANY_GSTIN}",
                S["company_sub"],
            ),
        ],
        [
            Paragraph("QUOTATION", S["doc_label"]),
            Paragraph(
                f"Quotation No: <b>{quotation.quotation_number}</b><br/>"
                f"Date: {quotation.created_at.strftime('%d %b %Y')}<br/>"
                f"Valid Until: {valid_until_str}<br/>"
                f"Status: {quotation.status.value.upper()}",
                S["doc_meta"],
            ),
        ],
    ]]

    header_table = Table(header_data, colWidths=[page_width * 0.6, page_width * 0.4])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_PRIMARY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (0, -1), 12),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 12),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 6))

    # ══════════════════════════════════════════════════════════════
    # BILL TO
    # ══════════════════════════════════════════════════════════════
    addr = ""
    if customer and customer.address:
        if isinstance(customer.address, dict):
            parts = [
                customer.address.get("line1", ""),
                customer.address.get("line2", ""),
                customer.address.get("city", ""),
                customer.address.get("state", ""),
                customer.address.get("pincode", ""),
            ]
            addr = ", ".join(p for p in parts if p)
        else:
            addr = str(customer.address)

    customer_name = customer.name if customer else "N/A"
    customer_phone = (customer.phone or "N/A") if customer else "N/A"
    customer_email = (customer.email or "N/A") if customer else "N/A"

    bill_to = (
        f"<b>{customer_name}</b><br/>"
        f"{addr}<br/>"
        f"Phone: {customer_phone}<br/>"
        f"Email: {customer_email}"
    )
    if customer and customer.gstin:
        bill_to += f"<br/>GSTIN: {customer.gstin}"

    gst_type_text = "Inter-State Supply (IGST)" if quotation.is_inter_state else "Intra-State Supply (CGST + SGST)"

    billing_data = [[
        [Paragraph("QUOTED TO", S["section_header"]), Paragraph(bill_to, S["body"])],
        [Paragraph("SUPPLY TYPE", S["section_header"]), Paragraph(gst_type_text, S["body"])],
    ]]

    billing_table = Table(billing_data, colWidths=[page_width * 0.6, page_width * 0.4])
    billing_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (0, -1), 10),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 10),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("LINEAFTER", (0, 0), (0, -1), 0.5, COLOR_BORDER),
    ]))
    story.append(billing_table)
    story.append(Spacer(1, 8))

    # ══════════════════════════════════════════════════════════════
    # ITEMS TABLE
    # ══════════════════════════════════════════════════════════════
    col_widths = [
        page_width * 0.05,
        page_width * 0.30,
        page_width * 0.10,
        page_width * 0.10,
        page_width * 0.20,
        page_width * 0.25,
    ]

    item_header = [
        Paragraph("#", S["bold"]),
        Paragraph("Product / Description", S["bold"]),
        Paragraph("HSN Code", S["bold"]),
        Paragraph("Qty", S["bold"]),
        Paragraph("Unit Price (₹)", S["bold"]),
        Paragraph("Amount (₹)", S["bold"]),
    ]

    item_rows = [item_header]
    for idx, item in enumerate(items, start=1):
        product_name = item.product_name
        hsn_code = str(item.hsn_code) if item.hsn_code else "-"
        item_rows.append([
            Paragraph(str(idx), S["body"]),
            Paragraph(product_name, S["body"]),
            Paragraph(hsn_code, S["body"]),
            Paragraph(str(item.quantity), S["body"]),
            Paragraph(f"₹{float(item.unit_price):,.2f}", S["body"]),
            Paragraph(f"₹{float(item.line_total):,.2f}", S["body"]),
        ])

    items_table = Table(item_rows, colWidths=col_widths, repeatRows=1)
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_SECONDARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), COLOR_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COLOR_WHITE, COLOR_LIGHT]),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, COLOR_BORDER),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (4, -1), "CENTER"),
        ("ALIGN", (5, 0), (5, -1), "RIGHT"),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 8))

    # ══════════════════════════════════════════════════════════════
    # TOTALS
    # ══════════════════════════════════════════════════════════════
    subtotal = float(quotation.subtotal_amount)
    tax_total = float(quotation.tax_amount)
    total = float(quotation.total_amount)

    summary_rows = [
        ["", "", Paragraph("Subtotal:", S["body"]), Paragraph(f"₹{subtotal:,.2f}", S["body"])],
    ]

    if quotation.is_inter_state:
        summary_rows.append([
            "", "",
            Paragraph(f"IGST @ {float(quotation.igst_rate):.0f}%:", S["body"]),
            Paragraph(f"₹{float(quotation.igst_amount):,.2f}", S["body"]),
        ])
    else:
        summary_rows.append([
            "", "",
            Paragraph(f"CGST @ {float(quotation.cgst_rate):.0f}%:", S["body"]),
            Paragraph(f"₹{float(quotation.cgst_amount):,.2f}", S["body"]),
        ])
        summary_rows.append([
            "", "",
            Paragraph(f"SGST @ {float(quotation.sgst_rate):.0f}%:", S["body"]),
            Paragraph(f"₹{float(quotation.sgst_amount):,.2f}", S["body"]),
        ])

    summary_table = Table(
        summary_rows,
        colWidths=[page_width * 0.25, page_width * 0.25, page_width * 0.28, page_width * 0.22],
    )
    summary_table.setStyle(TableStyle([
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("ALIGN", (3, 0), (3, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(summary_table)

    # Grand Total Banner
    grand_total_data = [[
        Paragraph("QUOTATION TOTAL", S["grand_total"]),
        Paragraph(f"₹{total:,.2f}", S["grand_total"]),
    ]]
    grand_total_table = Table(
        grand_total_data,
        colWidths=[page_width * 0.75, page_width * 0.25],
    )
    grand_total_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_ACCENT),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
    ]))
    story.append(Spacer(1, 4))
    story.append(grand_total_table)
    story.append(Spacer(1, 10))

    # ── Notes ──────────────────────────────────────────────────────
    if quotation.notes:
        story.append(Paragraph("NOTES", S["section_header"]))
        story.append(Paragraph(quotation.notes, S["body"]))
        story.append(Spacer(1, 8))

    # ══════════════════════════════════════════════════════════════
    # FOOTER
    # ══════════════════════════════════════════════════════════════
    story.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "This is a computer-generated quotation. Prices are subject to change after the validity date.",
        S["footer"],
    ))
    story.append(Paragraph(
        f"{COMPANY_NAME} | {COMPANY_ADDRESS_LINE2} | {COMPANY_PHONE} | {COMPANY_EMAIL}",
        S["footer"],
    ))

    # ── Build and save ─────────────────────────────────────────────
    doc.build(story)
    with open(file_path, "wb") as f:
        f.write(buffer.getvalue())

    return file_path
