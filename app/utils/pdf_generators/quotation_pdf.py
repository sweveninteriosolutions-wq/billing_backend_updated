import os
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import and_, select
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from app.models.quotation_models import Quotation, QuotationItem
from app.models.masters.customer_models import Customer
from app.models.masters.product_models import Product



async def generate_quotation_pdf(db: AsyncSession, quotation_id: int):
    """
    Generate a professional quotation PDF with customer info,
    items, GST, and total breakdown.
    """

    # -------------------------------
    # 1️⃣ Fetch quotation with related data
    # -------------------------------
    result = await db.execute(
        select(Quotation)
        .where(Quotation.id == quotation_id, Quotation.is_deleted == False)
    )
    quotation = result.scalars().first()

    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")

    # Fetch customer
    customer_result = await db.execute(
        select(Customer).where(Customer.id == quotation.customer_id)
    )
    customer = customer_result.scalars().first()

    # Fetch items
    item_result = await db.execute(
        select(QuotationItem)
        .where(QuotationItem.quotation_id == quotation.id, QuotationItem.is_deleted == False)
    )
    items = item_result.scalars().all()

    # -------------------------------
    # 2️⃣ Prepare file
    # -------------------------------
    os.makedirs("generated_pdfs", exist_ok=True)
    file_name = f"quotation_{quotation.quotation_number or quotation.id}.pdf"
    file_path = os.path.join("generated_pdfs", file_name)

    doc = SimpleDocTemplate(
        file_path,
        pagesize=A4,
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30,
    )
    styles = getSampleStyleSheet()
    elements = []

    # -------------------------------
    # 3️⃣ Header
    # -------------------------------
    elements.append(Paragraph("<b>Sweven Interio Solutions</b>", styles["Title"]))
    elements.append(Paragraph("Billing & Interior Design Solutions", styles["Normal"]))
    elements.append(Paragraph("Email: support@sweveninterio.com | Phone: +91 98765 43210", styles["Normal"]))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph(f"<b>Quotation #: </b>{quotation.quotation_number}", styles["Heading2"]))
    elements.append(Paragraph(f"Issue Date: {quotation.issue_date.strftime('%d-%m-%Y')}", styles["Normal"]))
    elements.append(Spacer(1, 10))

    # -------------------------------
    # 4️⃣ Customer Info
    # -------------------------------
    if customer:
        elements.append(Paragraph("<b>Customer Details</b>", styles["Heading3"]))
        elements.append(Paragraph(f"Name: {customer.name}", styles["Normal"]))
        elements.append(Paragraph(f"Email: {customer.email}", styles["Normal"]))
        elements.append(Paragraph(f"Phone: {customer.phone or '-'}", styles["Normal"]))

        # Address might be JSON
        address = customer.address
        if isinstance(address, dict):
            addr_str = ", ".join(v for v in address.values() if v)
        else:
            addr_str = str(address) if address else "-"
        elements.append(Paragraph(f"Address: {addr_str}", styles["Normal"]))
        elements.append(Spacer(1, 12))

    # -------------------------------
    # 5️⃣ Table Header
    # -------------------------------
    data = [["#", "Product", "Qty", "Unit Price", "Total (Excl. GST)"]]
    subtotal = 0

    for i, item in enumerate(items, start=1):
        # Try to fetch product for better name if available
        product_name = item.product_name
        product_result = await db.execute(select(Product).where(Product.id == item.product_id))
        product = product_result.scalars().first()
        if product and not product.is_deleted:
            product_name = product.name

        total = float(item.total or 0)
        subtotal += total

        data.append([
            i,
            product_name,
            item.quantity,
            f"₹{float(item.unit_price):.2f}",
            f"₹{total:.2f}",
        ])

    # -------------------------------
    # 6️⃣ Totals Section
    # -------------------------------
    gst_amt = float(quotation.gst_amount or 0)
    grand_total = float(quotation.total_amount or subtotal + gst_amt)

    data.append(["", "", "", "Subtotal", f"₹{subtotal:.2f}"])
    data.append(["", "", "", "GST (18%)", f"₹{gst_amt:.2f}"])
    data.append(["", "", "", "<b>Grand Total</b>", f"<b>₹{grand_total:.2f}</b>"])

    table = Table(data, colWidths=[25, 200, 60, 80, 80])
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
        ])
    )
    elements.append(table)
    elements.append(Spacer(1, 20))

    # -------------------------------
    # 7️⃣ Notes
    # -------------------------------
    if quotation.notes:
        elements.append(Paragraph("<b>Notes:</b>", styles["Heading3"]))
        elements.append(Paragraph(quotation.notes, styles["Normal"]))
        elements.append(Spacer(1, 12))

    elements.append(Paragraph("Thank you for choosing Sweven Interio Solutions!", styles["Normal"]))
    elements.append(Spacer(1, 12))

    # -------------------------------
    # ✅ Build PDF
    # -------------------------------
    doc.build(elements)
    return file_path
