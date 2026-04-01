# app/services/pdf_service.py
"""
PDF generation service — Jinja2 template + xhtml2pdf renderer.

Architecture:
  - _render_html()      : renders Jinja2 template → HTML string
  - _html_to_pdf_bytes(): converts HTML → PDF bytes  (engine: xhtml2pdf / pisa)
  - generate_pdf_from_context(): public API used by all routers

Swapping PDF engine for Linux/Docker (WeasyPrint):
    Replace _html_to_pdf_bytes() body with:
        from weasyprint import HTML
        return HTML(string=html, base_url=".").write_pdf()
    Then add weasyprint to requirements.txt and remove xhtml2pdf.
"""
import logging
from io import BytesIO
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

# ── Template directory: <project_root>/templates/ ─────────────────────────────
TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates"


# ──────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _get_jinja_env() -> Environment:
    """Build a Jinja2 environment pointed at the /templates directory."""
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _render_html(template_name: str, context: dict) -> str:
    """
    Render a Jinja2 template to an HTML string.

    Args:
        template_name: filename inside /templates/ (e.g. "invoice_template.html")
        context:       variables available inside the template

    Returns:
        Rendered HTML as a string.
    """
    env = _get_jinja_env()
    template = env.get_template(template_name)
    return template.render(**context)


def _html_to_pdf_bytes(html: str) -> bytes:
    """
    Convert an HTML string to PDF bytes using xhtml2pdf (pisa).

    xhtml2pdf is pure-Python and works on Windows without any system libraries.
    It uses the reportlab package (already in requirements.txt) under the hood.

    To switch to WeasyPrint on Linux/Docker, replace this entire function with:
        from weasyprint import HTML
        return HTML(string=html, base_url=".").write_pdf()
    """
    try:
        from xhtml2pdf import pisa  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "xhtml2pdf is not installed. "
            "Add 'xhtml2pdf==0.2.16' to requirements.txt and run pip install."
        ) from exc

    output = BytesIO()
    result = pisa.pisaDocument(
        BytesIO(html.encode("utf-8")),
        output,
        encoding="utf-8",
    )

    if result.err:
        raise RuntimeError(
            f"PDF generation failed with {result.err} error(s). "
            "Check template HTML for unsupported CSS or malformed tags."
        )

    return output.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ──────────────────────────────────────────────────────────────────────────────

def generate_pdf_from_context(template_name: str, context: dict) -> bytes:
    """
    Render a Jinja2 template and return PDF bytes.

    Args:
        template_name: filename inside /templates/ (e.g. "invoice_template.html")
        context:       dict of variables available in the template

    Returns:
        PDF bytes — pass directly to:
          Response(content=bytes, media_type="application/pdf", headers={...})

    Raises:
        RuntimeError: if PDF generation fails
        jinja2.TemplateNotFound: if the template file doesn't exist
    """
    logger.debug("Rendering template: %s", template_name)
    html = _render_html(template_name, context)

    logger.debug("Converting HTML to PDF (%d chars)", len(html))
    pdf_bytes = _html_to_pdf_bytes(html)

    logger.info(
        "PDF generated successfully: template=%s size=%d bytes",
        template_name,
        len(pdf_bytes),
    )
    return pdf_bytes
