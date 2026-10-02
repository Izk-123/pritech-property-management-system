"""
Shared ReportLab infrastructure.

Every PDF document in Pritech PMS is built on this base:

  - Registers DejaVu fonts once (Unicode-safe for English + Chichewa).
  - Provides a common stylesheet matching the platform's purple palette.
  - Exposes a `build_pdf()` helper that handles the file buffer,
    page decoration (header, footer, page numbers), and metadata.
  - Injects the current tenant's branding (logo, name, colours)
    into every page automatically.
"""
from io import BytesIO
from pathlib import Path

from django.db import connection
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer,
)


FONT_DIR = Path(__file__).parent / 'fonts'

_FONT_NAMES = {
    'DejaVu':       'DejaVuSans.ttf',
    'DejaVu-Bold':  'DejaVuSans-Bold.ttf',
    'DejaVu-Italic': 'DejaVuSans-Oblique.ttf',
    'DejaVu-BoldItalic': 'DejaVuSans-BoldOblique.ttf',
}

_fonts_registered = False


def register_fonts():
    """Register DejaVu fonts once per process. Idempotent."""
    global _fonts_registered
    if _fonts_registered:
        return

    for name, filename in _FONT_NAMES.items():
        path = FONT_DIR / filename
        if path.exists():
            pdfmetrics.registerFont(TTFont(name, str(path)))
        else:
            import logging
            logging.getLogger(__name__).warning(
                f'Font file missing: {path}. Falling back to Helvetica.'
            )

    try:
        pdfmetrics.registerFontFamily(
            'DejaVu',
            normal='DejaVu',
            bold='DejaVu-Bold',
            italic='DejaVu-Italic',
            boldItalic='DejaVu-BoldItalic',
        )
    except Exception:
        pass

    _fonts_registered = True


COLOR_PRIMARY    = colors.HexColor('#9333ea')
COLOR_PRIMARY_DK = colors.HexColor('#6b21a8')
COLOR_INK        = colors.HexColor('#0f172a')
COLOR_MUTED      = colors.HexColor('#64748b')
COLOR_BORDER     = colors.HexColor('#e2e8f0')
COLOR_BG_SOFT    = colors.HexColor('#f8fafc')
COLOR_SUCCESS    = colors.HexColor('#059669')
COLOR_DANGER     = colors.HexColor('#dc2626')
COLOR_WARNING    = colors.HexColor('#d97706')


def get_styles():
    """Return a dict of named ParagraphStyles used by every document."""
    register_fonts()
    base = getSampleStyleSheet()
    styles = {
        'title': ParagraphStyle(
            'PritechTitle', parent=base['Normal'],
            fontName='DejaVu-Bold', fontSize=22, leading=28,
            textColor=COLOR_INK, spaceAfter=2,
        ),
        'subtitle': ParagraphStyle(
            'PritechSubtitle', parent=base['Normal'],
            fontName='DejaVu', fontSize=10, leading=14,
            textColor=COLOR_MUTED, spaceAfter=14,
        ),
        'h1': ParagraphStyle(
            'PritechH1', parent=base['Normal'],
            fontName='DejaVu-Bold', fontSize=16, leading=22,
            textColor=COLOR_INK, spaceBefore=14, spaceAfter=6,
        ),
        'h2': ParagraphStyle(
            'PritechH2', parent=base['Normal'],
            fontName='DejaVu-Bold', fontSize=12, leading=18,
            textColor=COLOR_PRIMARY_DK, spaceBefore=10, spaceAfter=4,
        ),
        'body': ParagraphStyle(
            'PritechBody', parent=base['Normal'],
            fontName='DejaVu', fontSize=10, leading=15,
            textColor=COLOR_INK,
        ),
        'body_small': ParagraphStyle(
            'PritechBodySmall', parent=base['Normal'],
            fontName='DejaVu', fontSize=8, leading=12,
            textColor=COLOR_MUTED,
        ),
        'label': ParagraphStyle(
            'PritechLabel', parent=base['Normal'],
            fontName='DejaVu-Bold', fontSize=8, leading=11,
            textColor=COLOR_MUTED,
        ),
        'value': ParagraphStyle(
            'PritechValue', parent=base['Normal'],
            fontName='DejaVu', fontSize=10, leading=14,
            textColor=COLOR_INK,
        ),
        'right': ParagraphStyle(
            'PritechRight', parent=base['Normal'],
            fontName='DejaVu', fontSize=10, leading=14,
            textColor=COLOR_INK, alignment=TA_RIGHT,
        ),
        'right_bold': ParagraphStyle(
            'PritechRightBold', parent=base['Normal'],
            fontName='DejaVu-Bold', fontSize=11, leading=14,
            textColor=COLOR_INK, alignment=TA_RIGHT,
        ),
        'center': ParagraphStyle(
            'PritechCenter', parent=base['Normal'],
            fontName='DejaVu', fontSize=10, leading=14,
            textColor=COLOR_INK, alignment=TA_CENTER,
        ),
        'legal': ParagraphStyle(
            'PritechLegal', parent=base['Normal'],
            fontName='DejaVu', fontSize=8, leading=11,
            textColor=COLOR_MUTED, alignment=TA_LEFT,
        ),
    }
    return styles


def get_tenant_branding():
    """Return a dict describing the current tenant's branding."""
    tenant = getattr(connection, 'tenant', None)
    branding = {
        'name': 'Pritech PMS',
        'address': '',
        'phone': '',
        'email': '',
        'logo_path': None,
        'tin': '',
        'vat_number': '',
    }
    if not tenant:
        return branding

    branding['name'] = tenant.name
    branding['phone'] = getattr(tenant, 'contact_phone', '') or ''
    branding['email'] = getattr(tenant, 'contact_email', '') or ''

    logo = getattr(tenant, 'logo', None)
    if logo and hasattr(logo, 'path'):
        import os
        if os.path.exists(logo.path):
            branding['logo_path'] = logo.path

    return branding


def _draw_header_footer(canvas, doc):
    """Draw a header strip and footer on every page."""
    from datetime import datetime
    from reportlab.lib.utils import ImageReader

    register_fonts()
    canvas.saveState()

    page_width, page_height = A4
    left = 20 * mm
    right = page_width - 20 * mm

    branding = getattr(doc, '_tenant_branding', {}) or {}
    doc_title = getattr(doc, '_doc_title', '')

    header_top = page_height - 15 * mm

    canvas.setFont('DejaVu-Bold', 13)
    canvas.setFillColor(COLOR_INK)
    canvas.drawString(left, header_top, branding.get('name', 'Pritech PMS'))

    contact_bits = [
        branding.get('phone') or '',
        branding.get('email') or '',
    ]
    contact_line = ' - '.join(b for b in contact_bits if b)
    if contact_line:
        canvas.setFont('DejaVu', 8)
        canvas.setFillColor(COLOR_MUTED)
        canvas.drawString(left, header_top - 5 * mm, contact_line)

    if doc_title:
        canvas.setFont('DejaVu-Bold', 12)
        canvas.setFillColor(COLOR_PRIMARY_DK)
        canvas.drawRightString(right, header_top, doc_title.upper())

    logo_path = branding.get('logo_path')
    if logo_path:
        try:
            img = ImageReader(logo_path)
            iw, ih = img.getSize()
            max_w = 30 * mm
            max_h = 12 * mm
            scale = min(max_w / iw, max_h / ih)
            w, h = iw * scale, ih * scale
            canvas.drawImage(
                logo_path, right - w, header_top - h + 2 * mm,
                width=w, height=h,
                preserveAspectRatio=True, mask='auto',
            )
        except Exception:
            pass

    canvas.setStrokeColor(COLOR_BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(left, header_top - 9 * mm, right, header_top - 9 * mm)

    footer_top = 15 * mm

    canvas.setStrokeColor(COLOR_BORDER)
    canvas.line(left, footer_top + 4 * mm, right, footer_top + 4 * mm)

    canvas.setFont('DejaVu', 7.5)
    canvas.setFillColor(COLOR_MUTED)
    canvas.drawString(
        left, footer_top,
        'Generated ' + datetime.now().strftime('%d %b %Y  %H:%M'),
    )
    canvas.drawCentredString(
        page_width / 2, footer_top,
        'Pritech PMS - Property Management System',
    )
    canvas.drawRightString(
        right, footer_top,
        'Page ' + str(canvas.getPageNumber()),
    )

    canvas.restoreState()


def build_pdf(story, title='Document', subject='', author=None):
    """Render flowables into a PDF and return the bytes."""
    register_fonts()
    branding = get_tenant_branding()
    buffer = BytesIO()

    doc = BaseDocTemplate(
        buffer, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=30 * mm, bottomMargin=25 * mm,
        title=title, subject=subject,
        author=author or branding.get('name', 'Pritech PMS'),
        creator='Pritech PMS',
    )

    doc._tenant_branding = branding
    doc._doc_title = title

    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        id='normal', showBoundary=0,
    )

    doc.addPageTemplates([
        PageTemplate(id='main', frames=[frame], onPage=_draw_header_footer),
    ])

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes