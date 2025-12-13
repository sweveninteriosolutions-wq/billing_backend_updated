# app/utils/pdf_generators/invoice_pdf.py
import os
from decimal import Decimal
from fastapi import HTTPException
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from sqlalchemy.future import select

from app.models.invoice_models import Invoice
from app.models.masters.customer_models import Customer
from app.models.quotation_models import Quotation, QuotationItem

INVOICE_DIR = "generated_pdfs"


async def generate_invoice_pdf(db, invoice_id: int) -> str:
    """
    Generate a detailed PDF invoice with customer, quotation items, and payment details.
    """

    # --- Fetch invoice ---
    result = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.unique().scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # --- Fetch related entities ---
    customer = invoice.customer
    quotation = invoice.quotation
    items = quotation.items if quotation else []

    # --- Ensure output directory ---
    os.makedirs(INVOICE_DIR, exist_ok=True)
    file_path = os.path.join(INVOICE_DIR, f"Invoice_{invoice.invoice_number}.pdf")

    # --- Styles ---
    styles = getSampleStyleSheet()
    story = []

    # -----------------------------
    # HEADER
    # -----------------------------
    story.append(Paragraph(f"<b>INVOICE #{invoice.invoice_number}</b>", styles["Title"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"Status: {invoice.status.value.upper()}", styles["Normal"]))
    story.append(Paragraph(f"Date: {invoice.created_at.strftime('%d-%m-%Y')}", styles["Normal"]))
    story.append(Spacer(1, 15))

    # -----------------------------
    # CUSTOMER INFO
    # -----------------------------
    story.append(Paragraph("<b>Customer Details:</b>", styles["Heading3"]))
    story.append(Paragraph(f"Name: {customer.name}", styles["Normal"]))
    story.append(Paragraph(f"Email: {customer.email}", styles["Normal"]))
    story.append(Paragraph(f"Phone: {customer.phone or 'N/A'}", styles["Normal"]))
    story.append(Paragraph(f"Address: {customer.address or 'N/A'}", styles["Normal"]))
    story.append(Spacer(1, 15))

    # -----------------------------
    # QUOTATION ITEMS
    # -----------------------------
    story.append(Paragraph("<b>Quotation Items:</b>", styles["Heading3"]))
    data = [["Product", "Qty", "Unit Price", "Total"]]

    for item in items:
        data.append([
            item.product_name,
            str(item.quantity),
            f"₹ {float(item.unit_price):.2f}",
            f"₹ {float(item.total):.2f}",
        ])

    table = Table(data, colWidths=[180, 60, 100, 100])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
    ]))
    story.append(table)
    story.append(Spacer(1, 20))

    # -----------------------------
    # PAYMENT / FINANCIAL SUMMARY
    # -----------------------------
    story.append(Paragraph("<b>Payment Summary:</b>", styles["Heading3"]))

    # Handle missing or Decimal fields safely
    total_amount = float(invoice.total_amount or Decimal("0.00"))
    discounted_amount = float(invoice.discounted_amount or Decimal("0.00"))
    total_paid = float(invoice.total_paid or Decimal("0.00"))
    balance_due = float(invoice.balance_due or Decimal("0.00"))

    story.append(Paragraph(f"Total Amount: ₹ {total_amount:.2f}", styles["Normal"]))
    story.append(Paragraph(f"Discounted Amount: ₹ {discounted_amount:.2f}", styles["Normal"]))
    story.append(Paragraph(f"Total Paid: ₹ {total_paid:.2f}", styles["Normal"]))
    story.append(Paragraph(f"<b>Balance Due: ₹ {balance_due:.2f}</b>", styles["Heading2"]))
    story.append(Spacer(1, 20))

    # -----------------------------
    # FOOTER
    # -----------------------------
    story.append(Paragraph("Thank you for your business!", styles["Italic"]))
    story.append(Paragraph("For any support, contact our billing department.", styles["Normal"]))

    # -----------------------------
    # GENERATE PDF
    # -----------------------------
    doc = SimpleDocTemplate(file_path, pagesize=A4)
    doc.build(story)

    return file_path
