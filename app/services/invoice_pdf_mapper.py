# app/services/invoice_pdf_mapper.py
"""
Maps Invoice / Quotation ORM objects to clean Python dicts for the PDF template.

RULE: NO SQLAlchemy ORM objects are ever passed to the template.
      All relationships are explicitly loaded via selectinload() before mapping.
      Every value passed to the template is a plain Python type (str, int, float, None).
"""
import base64
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.billing.invoice_models import Invoice, InvoiceItem
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
    LOGO_PATH,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _load_logo_base64(path: str) -> Optional[str]:
    """
    Load a logo image file and return it as a base64-encoded string.
    Returns None (no crash) if the file is missing — template renders without logo.
    """
    try:
        p = Path(path)
        if p.exists():
            return base64.b64encode(p.read_bytes()).decode("utf-8")
        logger.warning("Logo file not found: %s", path)
    except Exception as exc:
        logger.warning("Could not load logo from %s: %s", path, exc)
    return None


def _format_address(address) -> str:
    """Flatten a customer address JSON blob or string into a single-line string."""
    if not address:
        return ""
    if isinstance(address, dict):
        parts = [
            address.get("line1", ""),
            address.get("line2", ""),
            address.get("city", ""),
            address.get("state", ""),
            address.get("pincode", ""),
        ]
        return ", ".join(p for p in parts if p)
    return str(address)


def _company_dict() -> dict:
    """Build the company info dict from config constants."""
    return {
        "name": COMPANY_NAME,
        "gstin": COMPANY_GSTIN,
        "address_line1": COMPANY_ADDRESS_LINE1,
        "address_line2": COMPANY_ADDRESS_LINE2,
        "phone": COMPANY_PHONE,
        "phone2": None,           # add COMPANY_PHONE2 to config.py if needed
        "email": COMPANY_EMAIL,
        "partners": "N.Shankar, I.Venugopal",   # override via env/config if needed
    }


# ──────────────────────────────────────────────────────────────────────────────
# INVOICE MAPPER
# ──────────────────────────────────────────────────────────────────────────────

async def build_invoice_pdf_context(db: AsyncSession, invoice_id: int) -> dict:
    """
    Fetch an invoice from the database and build a clean template context dict.

    Loads:  Invoice → customer, items → product, payments
    Returns: flat dict with only plain Python types — safe to pass to Jinja2.

    Raises:
        AppException(404) if the invoice doesn't exist or is soft-deleted.
    """
    result = await db.execute(
        select(Invoice)
        .options(
            selectinload(Invoice.customer),
            selectinload(Invoice.items).selectinload(InvoiceItem.product),
            selectinload(Invoice.payments),
        )
        .where(Invoice.id == invoice_id, Invoice.is_deleted.is_(False))
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise AppException(404, "Invoice not found", ErrorCode.INVOICE_NOT_FOUND)

    customer = invoice.customer
    items = [i for i in invoice.items if not i.is_deleted]

    item_list = []
    for item in items:
        product = item.product
        item_list.append({
            "name": product.name if product else f"Product #{item.product_id}",
            "description": (product.description or None) if product else None,
            "hsn_code": str(product.hsn_code) if (product and product.hsn_code) else None,
            "quantity": item.quantity,
            "unit_price": float(item.unit_price),
            "line_total": float(item.line_total),
        })

    return {
        "doc_type": "Invoice",
        "document_number": invoice.invoice_number,
        "date": invoice.created_at.strftime("%d/%m/%Y") if invoice.created_at else "",
        "valid_until": None,
        "status": invoice.status.value,
        "company": _company_dict(),
        "logo_base64": _load_logo_base64(LOGO_PATH),
        "customer": {
            "name": customer.name if customer else "",
            "gstin": (customer.gstin or None) if customer else None,
            "phone": (customer.phone or None) if customer else None,
            "email": (customer.email or None) if customer else None,
            "address": _format_address(customer.address if customer else None),
        },
        "items": item_list,
        # ── amounts ──────────────────────────────────────────────────────────
        "subtotal": float(invoice.gross_amount),
        "discount": float(invoice.discount_amount),
        "is_inter_state": invoice.is_inter_state,
        "cgst_rate": float(invoice.cgst_rate),
        "sgst_rate": float(invoice.sgst_rate),
        "igst_rate": float(invoice.igst_rate),
        "cgst_amount": float(invoice.cgst_amount),
        "sgst_amount": float(invoice.sgst_amount),
        "igst_amount": float(invoice.igst_amount),
        "tax_amount": float(invoice.tax_amount),
        "total": float(invoice.net_amount),
        "total_paid": float(invoice.total_paid),
        "balance_due": float(invoice.balance_due),
        "notes": None,
    }


# ──────────────────────────────────────────────────────────────────────────────
# QUOTATION MAPPER
# ──────────────────────────────────────────────────────────────────────────────

async def build_quotation_pdf_context(db: AsyncSession, quotation_id: int) -> dict:
    """
    Fetch a quotation from the database and build a clean template context dict.

    Loads:  Quotation → customer, items → product
    Returns: flat dict with only plain Python types — safe to pass to Jinja2.

    Raises:
        AppException(404) if the quotation doesn't exist or is soft-deleted.
    """
    result = await db.execute(
        select(Quotation)
        .options(
            selectinload(Quotation.customer),
            selectinload(Quotation.items).selectinload(QuotationItem.product),
        )
        .where(Quotation.id == quotation_id, Quotation.is_deleted.is_(False))
    )
    quotation = result.scalar_one_or_none()
    if not quotation:
        raise AppException(404, "Quotation not found", ErrorCode.QUOTATION_NOT_FOUND)

    customer = quotation.customer
    items = [i for i in quotation.items if not i.is_deleted]

    item_list = []
    for item in items:
        product = item.product
        item_list.append({
            "name": item.product_name,
            "description": (product.description or None) if product else None,
            "hsn_code": str(item.hsn_code) if item.hsn_code else None,
            "quantity": item.quantity,
            "unit_price": float(item.unit_price),
            "line_total": float(item.line_total),
        })

    valid_until_str = (
        quotation.valid_until.strftime("%d/%m/%Y") if quotation.valid_until else None
    )

    return {
        "doc_type": "Quotation",
        "document_number": quotation.quotation_number,
        "date": quotation.created_at.strftime("%d/%m/%Y") if quotation.created_at else "",
        "valid_until": valid_until_str,
        "status": quotation.status.value,
        "company": _company_dict(),
        "logo_base64": _load_logo_base64(LOGO_PATH),
        "customer": {
            "name": customer.name if customer else "",
            "gstin": (customer.gstin or None) if customer else None,
            "phone": (customer.phone or None) if customer else None,
            "email": (customer.email or None) if customer else None,
            "address": _format_address(customer.address if customer else None),
        },
        "items": item_list,
        # ── amounts ──────────────────────────────────────────────────────────
        "subtotal": float(quotation.subtotal_amount),
        "discount": 0.0,
        "is_inter_state": quotation.is_inter_state,
        "cgst_rate": float(quotation.cgst_rate),
        "sgst_rate": float(quotation.sgst_rate),
        "igst_rate": float(quotation.igst_rate),
        "cgst_amount": float(quotation.cgst_amount),
        "sgst_amount": float(quotation.sgst_amount),
        "igst_amount": float(quotation.igst_amount),
        "tax_amount": float(quotation.tax_amount),
        "total": float(quotation.total_amount),
        "total_paid": None,
        "balance_due": None,
        "notes": quotation.notes,
    }


# ──────────────────────────────────────────────────────────────────────────────
# MOCK DATA (for /pdf/test-invoice)
# ──────────────────────────────────────────────────────────────────────────────

def build_mock_pdf_context() -> dict:
    """
    Return a fully populated mock context for instant PDF testing.
    No database required — uses hardcoded Varasidhi Furniture sample data.
    """
    return {
        "doc_type": "Invoice",
        "document_number": "INV-TEST-0001",
        "date": "01/04/2026",
        "valid_until": None,
        "status": "verified",
        "company": _company_dict(),
        "logo_base64": _load_logo_base64(LOGO_PATH),
        "customer": {
            "name": "Ramesh Kumar & Sons",
            "gstin": "37AABCF1234D1Z1",
            "phone": "+91 99887 76655",
            "email": "ramesh@example.com",
            "address": "12-3-456, MG Road, Palakol, West Godavari, AP - 534 260",
        },
        "items": [
            {
                "name": "Wooden King Bed",
                "description": "Sheesham solid wood, queen size, polished finish",
                "hsn_code": "9403",
                "quantity": 1,
                "unit_price": 28000.00,
                "line_total": 28000.00,
            },
            {
                "name": "3-Door Wardrobe",
                "description": "With centre mirror, engineered wood",
                "hsn_code": "9403",
                "quantity": 1,
                "unit_price": 18500.00,
                "line_total": 18500.00,
            },
            {
                "name": "Coffee Table",
                "description": "Glass top, powder-coated metal legs",
                "hsn_code": "9403",
                "quantity": 2,
                "unit_price": 4200.00,
                "line_total": 8400.00,
            },
        ],
        "subtotal": 54900.00,
        "discount": 0.0,
        "is_inter_state": False,
        "cgst_rate": 9.0,
        "sgst_rate": 9.0,
        "igst_rate": 0.0,
        "cgst_amount": 4941.00,
        "sgst_amount": 4941.00,
        "igst_amount": 0.0,
        "tax_amount": 9882.00,
        "total": 64782.00,
        "total_paid": 20000.00,
        "balance_due": 44782.00,
        "notes": "Delivery within 7 working days. Installation included. Warranty: 2 years.",
    }
