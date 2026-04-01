# app/utils/pdf_generators/invoice_pdf.py
# Production-grade branded GST invoice PDF generator for Varasidhi Furnitures
#
# ERP-030 FIXED: Branding constants now imported from app.core.config instead of
#                reading os.getenv() directly. This was a config split-brain: the
#                quotation PDF already used config.py; the invoice PDF did not.

import os
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.billing.invoice_models import Invoice, InvoiceItem
from app.models.masters.customer_models import Customer
from app.core.exceptions import AppException
from app.constants.error_codes import ErrorCode

# ERP-030 FIXED: Import all branding constants from the single config source.
from app.core.config import (
    COMPANY_NAME,
    COMPANY_GSTIN,
    COMPANY_ADDRESS_LINE1,
    COMPANY_ADDRESS_LINE2,
    COMPANY_PHONE,
    COMPANY_EMAIL,
    UPLOAD_BASE_DIR,
)

INVOICE_OUTPUT_DIR = os.path.join(UPLOAD_BASE_DIR, "invoices")

# ─────────────────────────────────────────────────────────────────
# COLOR PALETTE
# ─────────────────────────────────────────────────────────────────
COLOR_PRIMARY = colors.HexColor("#1a1a2e")
COLOR_SECONDARY = colors.HexColor("#16213e")
COLOR_ACCENT = colors.HexColor("#0f3460")
COLOR_LIGHT = colors.HexColor("#f5f5f5")
COLOR_BORDER = colors.HexColor("#cccccc")
COLOR_WHITE = colors.white
COLOR_TEXT = colors.HexColor("#333333")
COLOR_MUTED = colors.HexColor("#777777")


def _styles():
    return {
        "company_name": ParagraphStyle(
            "company_name",
            fontSize=18,
            fontName="Helvetica-Bold",
            textColor=COLOR_WHITE,
            alignment=TA_LEFT,
            spaceAfter=2,
        ),
        "company_sub": ParagraphStyle(
            "company_sub",
            fontSize=8,
            fontName="Helvetica",
            textColor=colors.HexColor("#cccccc"),
            alignment=TA_LEFT,
            leading=12,
        ),
        "invoice_label": ParagraphStyle(
            "invoice_label",
            fontSize=22,
            fontName="Helvetica-Bold",
            textColor=COLOR_WHITE,
            alignment=TA_RIGHT,
        ),
        "invoice_meta": ParagraphStyle(
            "invoice_meta",
            fontSize=8,
            fontName="Helvetica",
            textColor=colors.HexColor("#cccccc"),
            alignment=TA_RIGHT,
            leading=12,
        ),
        "section_header": ParagraphStyle(
            "section_header",
            fontSize=8,
            fontName="Helvetica-Bold",
            textColor=COLOR_ACCENT,
            spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "body",
            fontSize=9,
            fontName="Helvetica",
            textColor=COLOR_TEXT,
            leading=13,
        ),
        "bold": ParagraphStyle(
            "bold",
            fontSize=9,
            fontName="Helvetica-Bold",
            textColor=COLOR_TEXT,
        ),
        "total_label": ParagraphStyle(
            "total_label",
            fontSize=10,
            fontName="Helvetica-Bold",
            textColor=COLOR_TEXT,
            alignment=TA_RIGHT,
        ),
        "grand_total": ParagraphStyle(
            "grand_total",
            fontSize=12,
            fontName="Helvetica-Bold",
            textColor=COLOR_WHITE,
            alignment=TA_RIGHT,
        ),
        "footer": ParagraphStyle(
            "footer",
            fontSize=8,
            fontName="Helvetica",
            textColor=COLOR_MUTED,
            alignment=TA_CENTER,
        ),
    }


async def generate_invoice_pdf(db: AsyncSession, invoice_id: int) -> str:
    """
    Generate a branded GST-compliant PDF invoice.
    Returns the file path to the saved PDF.
    """
    result = await db.execute(
        select(Invoice)
        .options(
            selectinload(Invoice.items).selectinload(InvoiceItem.product),
            selectinload(Invoice.payments),
            selectinload(Invoice.customer),
        )
        .where(
            Invoice.id == invoice_id,
            Invoice.is_deleted.is_(False),
        )
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise AppException(404, "Invoice not found", ErrorCode.INVOICE_NOT_FOUND)

    customer = invoice.customer
    items = [i for i in invoice.items if not i.is_deleted]

    os.makedirs(INVOICE_OUTPUT_DIR, exist_ok=True)
    file_name = f"Invoice_{invoice.invoice_number}.pdf"
    file_path = os.path.join(INVOICE_OUTPUT_DIR, file_name)

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

    # ── HEADER BANNER ──────────────────────────────────────────────
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
            Paragraph("TAX INVOICE", S["invoice_label"]),
            Paragraph(
                f"Invoice No: <b>{invoice.invoice_number}</b><br/>"
                f"Date: {invoice.created_at.strftime('%d %b %Y')}<br/>"
                f"Status: {invoice.status.value.upper()}",
                S["invoice_meta"],
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

    # ── BILL TO ────────────────────────────────────────────────────
    addr = ""
    if customer.address:
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

    bill_to_content = (
        f"<b>{customer.name}</b><br/>"
        f"{addr}<br/>"
        f"Phone: {customer.phone or 'N/A'}<br/>"
        f"Email: {customer.email or 'N/A'}"
    )
    if customer.gstin:
        bill_to_content += f"<br/>GSTIN: {customer.gstin}"

    gst_type_text = "Inter-State Supply (IGST)" if invoice.is_inter_state else "Intra-State Supply (CGST + SGST)"

    billing_data = [[
        [Paragraph("BILL TO", S["section_header"]), Paragraph(bill_to_content, S["body"])],
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

    # ── ITEMS TABLE ────────────────────────────────────────────────
    col_widths = [
        page_width * 0.05, page_width * 0.35, page_width * 0.10,
        page_width * 0.10, page_width * 0.20, page_width * 0.20,
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
        product_name = item.product.name if item.product else f"Product #{item.product_id}"
        hsn_code = str(item.product.hsn_code) if item.product and item.product.hsn_code else "-"
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
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COLOR_WHITE, COLOR_LIGHT]),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
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

    # ── TOTALS ─────────────────────────────────────────────────────
    gross = float(invoice.gross_amount)
    discount = float(invoice.discount_amount)
    taxable = gross - discount
    cgst_amt = float(invoice.cgst_amount)
    sgst_amt = float(invoice.sgst_amount)
    igst_amt = float(invoice.igst_amount)
    tax_total = float(invoice.tax_amount)
    net = float(invoice.net_amount)
    paid = float(invoice.total_paid)
    balance = float(invoice.balance_due)

    totals_rows = [
        ["", "", Paragraph("Gross Amount:", S["body"]), Paragraph(f"₹{gross:,.2f}", S["body"])],
    ]
    if discount > 0:
        totals_rows.append(["", "", Paragraph("Discount:", S["body"]), Paragraph(f"- ₹{discount:,.2f}", S["body"])])
        totals_rows.append(["", "", Paragraph("Taxable Amount:", S["body"]), Paragraph(f"₹{taxable:,.2f}", S["body"])])
    if invoice.is_inter_state:
        totals_rows.append(["", "", Paragraph(f"IGST @ {float(invoice.igst_rate):.0f}%:", S["body"]), Paragraph(f"₹{igst_amt:,.2f}", S["body"])])
    else:
        totals_rows.append(["", "", Paragraph(f"CGST @ {float(invoice.cgst_rate):.0f}%:", S["body"]), Paragraph(f"₹{cgst_amt:,.2f}", S["body"])])
        totals_rows.append(["", "", Paragraph(f"SGST @ {float(invoice.sgst_rate):.0f}%:", S["body"]), Paragraph(f"₹{sgst_amt:,.2f}", S["body"])])
    totals_rows.append(["", "", Paragraph("Total Tax:", S["body"]), Paragraph(f"₹{tax_total:,.2f}", S["body"])])
    totals_rows.append(["", "", Paragraph("Total Paid:", S["body"]), Paragraph(f"₹{paid:,.2f}", S["body"])])

    summary_table = Table(totals_rows, colWidths=[
        page_width * 0.25, page_width * 0.25, page_width * 0.28, page_width * 0.22,
    ])
    summary_table.setStyle(TableStyle([
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("ALIGN", (3, 0), (3, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(summary_table)

    grand_total_data = [[
        Paragraph("BALANCE DUE" if balance > 0 else "TOTAL AMOUNT PAID", S["grand_total"]),
        Paragraph(f"₹{balance:,.2f}" if balance > 0 else f"₹{net:,.2f}", S["grand_total"]),
    ]]
    grand_total_table = Table(grand_total_data, colWidths=[page_width * 0.75, page_width * 0.25])
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

    # ── PAYMENT HISTORY ───────────────────────────────────────────
    if invoice.payments:
        story.append(Paragraph("PAYMENT HISTORY", S["section_header"]))
        story.append(Spacer(1, 4))
        pay_data = [[
            Paragraph("Date", S["bold"]),
            Paragraph("Method", S["bold"]),
            Paragraph("Amount (₹)", S["bold"]),
        ]]
        for p in invoice.payments:
            pay_data.append([
                Paragraph(p.created_at.strftime("%d %b %Y") if p.created_at else "-", S["body"]),
                Paragraph(p.payment_method or "-", S["body"]),
                Paragraph(f"₹{float(p.amount):,.2f}", S["body"]),
            ])
        pay_table = Table(pay_data, colWidths=[page_width * 0.3, page_width * 0.4, page_width * 0.3])
        pay_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_LIGHT),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, COLOR_BORDER),
            ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ]))
        story.append(pay_table)
        story.append(Spacer(1, 10))

    # ── FOOTER ────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Thank you for your purchase! This is a computer-generated invoice.",
        S["footer"],
    ))
    story.append(Paragraph(
        f"{COMPANY_NAME} | {COMPANY_ADDRESS_LINE2} | {COMPANY_PHONE} | {COMPANY_EMAIL}",
        S["footer"],
    ))

    doc.build(story)
    with open(file_path, "wb") as f:
        f.write(buffer.getvalue())

    return file_path
