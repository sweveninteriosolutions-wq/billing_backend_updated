# app/routers/pdf_router.py
"""
PDF generation endpoints.

Routes:
  GET /pdf/invoice/{invoice_id}        → renders invoice PDF (inline preview)
  GET /pdf/quotation/{quotation_id}    → renders quotation PDF (inline preview)
  GET /pdf/test-invoice                → renders mock PDF (no DB, instant test)

All endpoints return application/pdf with Content-Disposition: inline
so browsers open the PDF in-tab rather than downloading.
"""
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.utils.check_roles import require_role
from app.services.pdf_service import generate_pdf_from_context
from app.services.invoice_pdf_mapper import (
    build_invoice_pdf_context,
    build_quotation_pdf_context,
    build_mock_pdf_context,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/pdf",
    tags=["PDF Generation"],
)

TEMPLATE = "invoice_template.html"  # single reusable template for both doc types


def _pdf_response(pdf_bytes: bytes, filename: str) -> Response:
    """Wrap PDF bytes in a FastAPI Response with correct headers for inline preview."""
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            # 'inline' → browser opens in PDF viewer; change to 'attachment' to force download
            "Content-Disposition": f'inline; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# INVOICE PDF
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
    "/invoice/{invoice_id}",
    summary="Generate Invoice PDF",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "Invoice PDF"},
        404: {"description": "Invoice not found"},
    },
)
async def get_invoice_pdf(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "cashier", "manager"])),
):
    """
    Generate a PDF for the given invoice and return it for inline browser preview.

    Flow:
      1. Fetch invoice + customer + items + payments from DB
      2. Map ORM data → clean dict (no ORM objects in template)
      3. Render invoice_template.html with Jinja2
      4. Convert HTML → PDF bytes (xhtml2pdf)
      5. Return application/pdf response
    """
    context = await build_invoice_pdf_context(db, invoice_id)
    pdf_bytes = generate_pdf_from_context(TEMPLATE, context)
    filename = f"Invoice_{context['document_number']}.pdf"
    logger.info("Invoice PDF served: id=%d filename=%s", invoice_id, filename)
    return _pdf_response(pdf_bytes, filename)


# ──────────────────────────────────────────────────────────────────────────────
# QUOTATION PDF
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
    "/quotation/{quotation_id}",
    summary="Generate Quotation PDF",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "Quotation PDF"},
        404: {"description": "Quotation not found"},
    },
)
async def get_quotation_pdf(
    quotation_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "sales", "cashier", "manager"])),
):
    """
    Generate a PDF for the given quotation and return it for inline browser preview.

    Flow:
      1. Fetch quotation + customer + items from DB
      2. Map ORM data → clean dict
      3. Render invoice_template.html with Jinja2 (doc_type = "Quotation")
      4. Convert HTML → PDF bytes
      5. Return application/pdf response
    """
    context = await build_quotation_pdf_context(db, quotation_id)
    pdf_bytes = generate_pdf_from_context(TEMPLATE, context)
    filename = f"Quotation_{context['document_number']}.pdf"
    logger.info("Quotation PDF served: id=%d filename=%s", quotation_id, filename)
    return _pdf_response(pdf_bytes, filename)


# ──────────────────────────────────────────────────────────────────────────────
# TEST ENDPOINT — no auth, no DB, instant validation
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
    "/test-invoice",
    summary="Test Invoice PDF (mock data)",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "Test invoice PDF"},
    },
)
async def test_invoice_pdf():
    """
    Generate a test PDF using hardcoded mock data.

    No authentication, no database.
    Use this to validate the template + PDF engine are working correctly
    before testing with real data.

    Hit: GET /pdf/test-invoice
    """
    context = build_mock_pdf_context()
    pdf_bytes = generate_pdf_from_context(TEMPLATE, context)
    logger.info("Test invoice PDF generated (%d bytes)", len(pdf_bytes))
    return _pdf_response(pdf_bytes, "Test_Invoice_Varasidhi.pdf")
