# ============================================================
# create-pdf-modules.ps1
#
# Install PDF modules and wire them into config/urls.py.
# Run from project root:
#   powershell -ExecutionPolicy Bypass -File .\create-pdf-modules.ps1
#
# Save as ANSI or UTF-8 without BOM. Do not let your editor
# convert straight quotes to curly quotes.
# ============================================================

$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding $false

function New-PyFile {
    param([string]$Path, [string]$Content)
    $full = Join-Path $PWD $Path
    $dir = Split-Path $full -Parent
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    [System.IO.File]::WriteAllText($full, $Content, $utf8)
    Write-Host "  + $Path"
}

function Add-BlockOnce {
    param([string]$Path, [string]$Marker, [string]$Block)
    $full = Join-Path $PWD $Path
    if (Test-Path -LiteralPath $full) {
        $existing = [System.IO.File]::ReadAllText($full)
        if ($existing.Contains($Marker)) {
            Write-Host "  = $Path already has marker"
            return
        }
        Add-Content -Path $full -Value $Block -Encoding UTF8
        Write-Host "  + appended to $Path"
    } else {
        [System.IO.File]::WriteAllText($full, $Block.Trim(), $utf8)
        Write-Host "  + created $Path"
    }
}

# Delegate the URL merge to Python. Python's source-file parsing
# is unaffected by the encoding gremlins that break PowerShell's
# tokenizer when the file has smart quotes in it.
function Merge-UrlInclude {
    param([string]$Path)

    $full = Join-Path $PWD $Path
    if (-not (Test-Path -LiteralPath $full)) {
        Write-Host "  ! $Path not found - skipping"
        return
    }

    $q  = [char]39
    $nl = [char]10

    $py = ''
    $py += 'import sys' + $nl
    $py += 'from pathlib import Path' + $nl
    $py += 'p = Path(sys.argv[1])' + $nl
    $py += 't = p.read_text(encoding="utf-8")' + $nl
    $py += 'if "apps.core.documents.pdf.urls" in t:' + $nl
    $py += '    print("  = " + str(p) + " already wired")' + $nl
    $py += '    sys.exit(0)' + $nl
    $py += 'a = "path(' + $q + 'admin/' + $q + ', admin.site.urls)," ' + $nl
    $py += 'if a not in t:' + $nl
    $py += '    print("  ! admin anchor not found in " + str(p))' + $nl
    $py += '    sys.exit(1)' + $nl
    $py += 'i = "    # PDF documents' + $nl
    $py += '    path(' + $q + 'pdf/' + $q + ', include(' + $q + 'apps.core.documents.pdf.urls' + $q + ')),' + $nl + $nl + '"' + $nl
    $py += 'p.write_text(t.replace(a, i + a, 1), encoding="utf-8")' + $nl
    $py += 'print("  + wired pdf include into " + str(p))' + $nl

    $tmp = Join-Path $env:TEMP 'pritech_merge_urls.py'
    [System.IO.File]::WriteAllText($tmp, $py, $utf8)
    try {
        python $tmp $full
    } finally {
        Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue
    }
}


# ============================================================
# Folders
# ============================================================
Write-Host ''
Write-Host 'Creating folders...' -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path 'apps/core/documents/pdf/fonts' | Out-Null
New-Item -ItemType Directory -Force -Path 'tests/test_pdf'              | Out-Null


# ============================================================
# Python modules
# ============================================================
Write-Host ''
Write-Host 'Writing Python modules...' -ForegroundColor Cyan

New-PyFile -Path 'apps/core/documents/pdf/__init__.py' -Content ''


New-PyFile -Path 'apps/core/documents/pdf/base.py' -Content @'
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
'@


New-PyFile -Path 'apps/core/documents/pdf/folio.py' -Content @'
"""Folio invoice - generated at check-out."""
from datetime import datetime
from io import BytesIO

import qrcode
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image, Paragraph, Spacer, Table, TableStyle,
)

from .base import (
    COLOR_BG_SOFT, COLOR_BORDER, COLOR_DANGER, COLOR_INK, COLOR_MUTED,
    COLOR_PRIMARY, COLOR_PRIMARY_DK, COLOR_SUCCESS,
    build_pdf, get_styles, get_tenant_branding,
)


def _qr_image(data, size_mm=25):
    if not data:
        return None
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8, border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return Image(buf, width=size_mm * mm, height=size_mm * mm)


def _money(amount, currency='MWK'):
    try:
        return f'{currency} {amount:,.2f}'
    except (ValueError, TypeError):
        return f'{currency} 0.00'


def render_folio_invoice(folio):
    """Render a folio invoice to PDF bytes."""
    styles = get_styles()
    branding = get_tenant_branding()
    reservation = folio.reservation
    guest = reservation.primary_guest
    prop = reservation.property

    story = []
    story.append(Paragraph('Tax Invoice', styles['title']))
    story.append(Paragraph(
        f'Folio for reservation <b>{reservation.reservation_number}</b>',
        styles['subtitle'],
    ))
    story.append(Spacer(1, 4 * mm))

    billed_to = [
        Paragraph('BILLED TO', styles['label']),
        Paragraph(guest.full_name, styles['value']),
    ]
    if guest.phone_primary:
        billed_to.append(Paragraph(guest.phone_primary, styles['body_small']))
    if guest.email:
        billed_to.append(Paragraph(guest.email, styles['body_small']))

    stay_details = [
        Paragraph('STAY', styles['label']),
        Paragraph(
            f'<b>{reservation.check_in:%d %b %Y}</b> to '
            f'<b>{reservation.check_out:%d %b %Y}</b>',
            styles['value'],
        ),
        Paragraph(
            f'{reservation.nights} night'
            f'{"s" if reservation.nights != 1 else ""} - '
            f'{reservation.adults} adult'
            f'{"s" if reservation.adults != 1 else ""}',
            styles['body_small'],
        ),
        Paragraph(prop.name, styles['body_small']),
    ]

    header_table = Table(
        [[billed_to, stay_details]], colWidths=[95 * mm, 75 * mm],
    )
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 8 * mm))

    charge_rows = [[
        Paragraph('<b>DESCRIPTION</b>', styles['label']),
        Paragraph('<b>TYPE</b>', styles['label']),
        Paragraph('<b>AMOUNT</b>', styles['label']),
    ]]
    charges = folio.charges.all().order_by('created_at')
    for charge in charges:
        charge_rows.append([
            Paragraph(charge.description, styles['body']),
            Paragraph(charge.get_charge_type_display(), styles['body_small']),
            Paragraph(_money(charge.amount, charge.currency), styles['right']),
        ])
    if len(charge_rows) == 1:
        charge_rows.append([
            Paragraph('No charges on this folio.', styles['body_small']),
            '', '',
        ])

    charges_table = Table(
        charge_rows, colWidths=[105 * mm, 30 * mm, 35 * mm], repeatRows=1,
    )
    charges_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COLOR_BG_SOFT),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, COLOR_BORDER),
        ('LINEBELOW', (0, 1), (-1, -2), 0.25, COLOR_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3 * mm),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3 * mm),
        ('TOPPADDING', (0, 0), (-1, -1), 2 * mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2 * mm),
    ]))
    story.append(charges_table)
    story.append(Spacer(1, 6 * mm))

    payments = folio.payments.all().order_by('created_at')
    if payments.exists():
        payment_rows = [[
            Paragraph('<b>PAYMENTS RECEIVED</b>', styles['label']),
            Paragraph('<b>REFERENCE</b>', styles['label']),
            Paragraph('<b>AMOUNT</b>', styles['label']),
        ]]
        for payment in payments:
            payment_rows.append([
                Paragraph(payment.get_method_display(), styles['body']),
                Paragraph(payment.reference or '-', styles['body_small']),
                Paragraph(_money(payment.amount, payment.currency),
                          styles['right']),
            ])
        payments_table = Table(
            payment_rows, colWidths=[70 * mm, 65 * mm, 35 * mm], repeatRows=1,
        )
        payments_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COLOR_BG_SOFT),
            ('LINEBELOW', (0, 0), (-1, 0), 0.5, COLOR_BORDER),
            ('LINEBELOW', (0, 1), (-1, -2), 0.25, COLOR_BORDER),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 3 * mm),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3 * mm),
            ('TOPPADDING', (0, 0), (-1, -1), 2 * mm),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2 * mm),
        ]))
        story.append(payments_table)
        story.append(Spacer(1, 6 * mm))

    balance = folio.balance
    balance_label = 'AMOUNT DUE' if balance > 0 else 'BALANCE'
    balance_colour = COLOR_DANGER if balance > 0 else COLOR_SUCCESS

    summary_data = [
        [Paragraph('<b>TOTAL CHARGES</b>', styles['label']),
         Paragraph(_money(folio.total_charges, folio.currency),
                   styles['right'])],
        [Paragraph('<b>TOTAL PAID</b>', styles['label']),
         Paragraph(_money(folio.total_payments, folio.currency),
                   styles['right'])],
        [Paragraph(f'<b>{balance_label}</b>', styles['label']),
         Paragraph(
             f'<font color="{balance_colour.hexval()}">'
             f'<b>{_money(balance, folio.currency)}</b></font>',
             styles['right_bold'],
         )],
    ]
    summary_table = Table(summary_data, colWidths=[120 * mm, 50 * mm],
                          hAlign='RIGHT')
    summary_table.setStyle(TableStyle([
        ('LINEABOVE', (0, 2), (-1, 2), 0.75, COLOR_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 2 * mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2 * mm),
        ('LEFTPADDING', (0, 0), (-1, -1), 3 * mm),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3 * mm),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 10 * mm))

    try:
        from apps.compliance.eis.models import EISInvoiceLog
        from django.contrib.contenttypes.models import ContentType
        eis_log = EISInvoiceLog.objects.filter(
            content_type=ContentType.objects.get_for_model(folio),
            object_id=folio.pk,
            submission_status=EISInvoiceLog.SubmissionStatus.VALIDATED,
        ).first()
    except Exception:
        eis_log = None

    if eis_log:
        qr_flowable = _qr_image(
            getattr(eis_log, 'mra_validation_url', '')
            or eis_log.mra_invoice_number,
            size_mm=28,
        )
        mra_block = [
            Paragraph('MALAWI REVENUE AUTHORITY', styles['label']),
            Paragraph(f'<b>Invoice No:</b> {eis_log.mra_invoice_number}',
                      styles['value']),
            Paragraph(
                f'<b>Submitted:</b> '
                f'{eis_log.synced_at:%d %b %Y %H:%M}',
                styles['body_small'],
            ),
            Paragraph(
                'Scan the QR code to verify this invoice on the '
                'MRA Electronic Invoicing System.',
                styles['body_small'],
            ),
        ]
        if qr_flowable:
            mra_block.append(Spacer(1, 2 * mm))
            mra_block.append(qr_flowable)
        mra_table = Table([[mra_block]], colWidths=[170 * mm])
        mra_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), COLOR_BG_SOFT),
            ('BOX', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ('LEFTPADDING', (0, 0), (-1, -1), 4 * mm),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4 * mm),
            ('TOPPADDING', (0, 0), (-1, -1), 3 * mm),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3 * mm),
        ]))
        story.append(mra_table)
        story.append(Spacer(1, 6 * mm))

    story.append(Paragraph(
        'This is a computer-generated invoice. No signature required. '
        'Retain for your records.',
        styles['legal'],
    ))

    return build_pdf(
        story, title='Tax Invoice',
        subject=f'Folio {reservation.reservation_number}',
    )
'@


New-PyFile -Path 'apps/core/documents/pdf/receipt.py' -Content @'
"""Payment receipt."""
from datetime import datetime

from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from .base import (
    COLOR_BG_SOFT, COLOR_BORDER, COLOR_SUCCESS,
    build_pdf, get_styles, get_tenant_branding,
)


def render_payment_receipt(payment):
    styles = get_styles()
    folio = payment.folio
    reservation = folio.reservation
    guest = reservation.primary_guest

    story = []
    story.append(Paragraph('Payment Receipt', styles['title']))
    story.append(Paragraph(
        f'Folio <b>{reservation.reservation_number}</b>',
        styles['subtitle'],
    ))
    story.append(Spacer(1, 6 * mm))

    rows = [
        [Paragraph('RECEIVED FROM', styles['label']),
         Paragraph(guest.full_name, styles['value'])],
        [Paragraph('PROPERTY', styles['label']),
         Paragraph(reservation.property.name, styles['value'])],
        [Paragraph('DATE RECEIVED', styles['label']),
         Paragraph(f'{payment.created_at:%d %b %Y %H:%M}',
                   styles['value'])],
        [Paragraph('PAYMENT METHOD', styles['label']),
         Paragraph(payment.get_method_display(), styles['value'])],
    ]
    if payment.reference:
        rows.append([
            Paragraph('REFERENCE', styles['label']),
            Paragraph(payment.reference, styles['value']),
        ])

    meta_table = Table(rows, colWidths=[45 * mm, 125 * mm])
    meta_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 2 * mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2 * mm),
        ('LINEBELOW', (0, 0), (-1, -2), 0.25, COLOR_BORDER),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 8 * mm))

    amount_block = [
        Paragraph('AMOUNT RECEIVED', styles['label']),
        Spacer(1, 2 * mm),
        Paragraph(
            f'<font size="26" color="{COLOR_SUCCESS.hexval()}">'
            f'<b>{payment.currency} {payment.amount:,.2f}</b></font>',
            styles['center'],
        ),
    ]
    amount_table = Table([[amount_block]], colWidths=[170 * mm])
    amount_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COLOR_BG_SOFT),
        ('BOX', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 6 * mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6 * mm),
    ]))
    story.append(amount_table)
    story.append(Spacer(1, 8 * mm))

    remaining = folio.balance
    if remaining > 0:
        story.append(Paragraph(
            f'<b>Remaining balance:</b> '
            f'{payment.currency} {remaining:,.2f}',
            styles['body'],
        ))
    else:
        story.append(Paragraph('<b>Paid in full. Thank you.</b>',
                               styles['body']))

    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph(
        f'Receipt ID: {payment.id:08d} - Generated '
        f'{datetime.now().strftime("%d %b %Y %H:%M")}',
        styles['legal'],
    ))

    return build_pdf(
        story, title='Payment Receipt',
        subject=f'Folio {reservation.reservation_number}',
    )
'@


New-PyFile -Path 'apps/core/documents/pdf/lease.py' -Content @'
"""Lease agreement - multi-page, signable PDF."""
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak, Paragraph, Spacer, Table, TableStyle,
)

from .base import (
    COLOR_BG_SOFT, COLOR_BORDER, COLOR_MUTED,
    build_pdf, get_styles, get_tenant_branding,
)


def _kv_table(rows, styles):
    data = [
        [Paragraph(f'<b>{k}</b>', styles['label']),
         Paragraph(str(v), styles['value'])]
        for k, v in rows
    ]
    table = Table(data, colWidths=[55 * mm, 115 * mm])
    table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 2 * mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2 * mm),
        ('LINEBELOW', (0, 0), (-1, -2), 0.25, COLOR_BORDER),
    ]))
    return table


def render_lease_agreement(lease):
    styles = get_styles()
    branding = get_tenant_branding()

    story = []
    story.append(Paragraph('Residential Tenancy Agreement', styles['title']))
    story.append(Paragraph(f'Lease <b>{lease.lease_number}</b>',
                           styles['subtitle']))
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph('1. The Parties', styles['h1']))
    story.append(Paragraph(
        'This agreement is made between the following parties:',
        styles['body'],
    ))
    story.append(Spacer(1, 3 * mm))

    landlord = lease.landlord
    story.append(_kv_table([
        ('LANDLORD', landlord.full_name if landlord else branding['name']),
        ('LANDLORD CONTACT',
         (landlord.phone_primary if landlord
          else branding.get('phone', '')) or '-'),
        ('TENANT', lease.tenant.full_name),
        ('TENANT CONTACT', lease.tenant.phone_primary or '-'),
        ('PROPERTY', lease.unit.property.name),
        ('UNIT', lease.unit.identifier),
        ('PROPERTY ADDRESS', lease.unit.property.address or '-'),
    ], styles))

    story.append(PageBreak())

    story.append(Paragraph('2. Term, Rent, and Deposit', styles['h1']))
    story.append(_kv_table([
        ('LEASE START', lease.start_date.strftime('%d %B %Y')),
        ('LEASE END', lease.end_date.strftime('%d %B %Y')),
        ('RENT AMOUNT', f'{lease.rent_currency} {lease.rent_amount:,.2f}'),
        ('PAYMENT FREQUENCY', lease.get_payment_frequency_display()),
        ('RENT DUE ON', f'Day {lease.payment_due_day} of each period'),
        ('SECURITY DEPOSIT',
         f'{lease.rent_currency} {lease.deposit_amount:,.2f}'),
        ('GRACE PERIOD', f'{lease.grace_period_days} days'),
    ], styles))

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph('2.1 Rent Payment', styles['h2']))
    story.append(Paragraph(
        f'The Tenant shall pay rent of '
        f'{lease.rent_currency} {lease.rent_amount:,.2f} on or before '
        f'day {lease.payment_due_day} of each '
        f'{lease.get_payment_frequency_display().lower()} period.',
        styles['body'],
    ))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph('2.2 Security Deposit', styles['h2']))
    story.append(Paragraph(
        f'The Tenant shall pay a security deposit of '
        f'{lease.rent_currency} {lease.deposit_amount:,.2f} prior to '
        f'occupation. The deposit shall be refunded within 30 days of '
        f'vacation, less any legitimate deductions.',
        styles['body'],
    ))

    story.append(PageBreak())

    story.append(Paragraph('3. Obligations of the Parties', styles['h1']))
    story.append(Paragraph('3.1 The Landlord agrees to:', styles['h2']))
    for line in [
        'Deliver the property in a clean and habitable condition.',
        'Maintain the structure, roof, and exterior of the property.',
        'Ensure water and electricity connections are functioning.',
        'Provide at least 24 hours notice before entering the property.',
        'Refund the security deposit within 30 days of vacation.',
    ]:
        story.append(Paragraph(f'- {line}', styles['body']))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph('3.2 The Tenant agrees to:', styles['h2']))
    for line in [
        'Pay rent on time, in full, using the agreed method.',
        'Pay for water, electricity, and other utilities consumed.',
        'Keep the property clean and in good condition.',
        'Not sublet the property without written consent.',
        'Not make alterations without written consent.',
        'Report damage or maintenance issues promptly.',
    ]:
        story.append(Paragraph(f'- {line}', styles['body']))

    story.append(PageBreak())

    story.append(Paragraph('4. Signatures', styles['h1']))
    story.append(Paragraph(
        'By signing below, both parties agree to the terms set out in '
        'this agreement.',
        styles['body'],
    ))
    story.append(Spacer(1, 10 * mm))

    signature_data = [
        [Paragraph('<b>LANDLORD</b>', styles['label']),
         Paragraph('<b>TENANT</b>', styles['label'])],
        [Paragraph(
            f'{landlord.full_name if landlord else branding["name"]}',
            styles['value']),
         Paragraph(lease.tenant.full_name, styles['value'])],
        ['', ''],
        [Paragraph('Signature: _____________________', styles['body']),
         Paragraph('Signature: _____________________', styles['body'])],
        [Paragraph('Date: _____________________', styles['body']),
         Paragraph('Date: _____________________', styles['body'])],
    ]
    signature_table = Table(
        signature_data, colWidths=[85 * mm, 85 * mm],
        rowHeights=[None, None, 20 * mm, None, None],
    )
    signature_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 3 * mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3 * mm),
        ('LINEBELOW', (0, 2), (0, 2), 0.5, COLOR_MUTED),
        ('LINEBELOW', (1, 2), (1, 2), 0.5, COLOR_MUTED),
    ]))
    story.append(signature_table)

    story.append(Spacer(1, 12 * mm))
    story.append(Paragraph(
        f'This agreement is legally binding under the laws of Malawi. '
        f'Lease reference {lease.lease_number} - Generated by '
        f'Pritech PMS on behalf of {branding["name"]}.',
        styles['legal'],
    ))

    return build_pdf(
        story, title='Lease Agreement',
        subject=f'Lease {lease.lease_number}',
    )
'@


# ---- Stubs ----
New-PyFile -Path 'apps/core/documents/pdf/rent_invoice.py' -Content @'
"""Rent invoice PDF - STUB."""


def render_rent_invoice(invoice):
    raise NotImplementedError(
        'render_rent_invoice() is not implemented yet. '
        'See folio.py for the pattern.'
    )
'@


New-PyFile -Path 'apps/core/documents/pdf/sale_agreement.py' -Content @'
"""Sale agreement PDF - STUB."""


def render_sale_agreement(agreement):
    raise NotImplementedError(
        'render_sale_agreement() is not implemented yet. '
        'See lease.py for the pattern.'
    )
'@


New-PyFile -Path 'apps/core/documents/pdf/statements.py' -Content @'
"""Landlord / tenant statements PDF - STUB."""


def render_landlord_statement(prop, period_start, period_end):
    raise NotImplementedError(
        'render_landlord_statement() is not implemented yet.'
    )
'@


New-PyFile -Path 'apps/core/documents/pdf/views.py' -Content @'
"""Views that serve PDFs."""
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View

from apps.core.mixins import StaffRequiredMixin
from apps.hospitality.folios.models import Folio, FolioPayment
from apps.property.leases.models import Lease

from .folio import render_folio_invoice
from .receipt import render_payment_receipt
from .lease import render_lease_agreement


def _pdf_response(pdf_bytes, filename, inline=True):
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    disposition = 'inline' if inline else 'attachment'
    response['Content-Disposition'] = (
        f'{disposition}; filename="{filename}"'
    )
    response['Cache-Control'] = 'private, no-store'
    return response


class FolioInvoicePDFView(StaffRequiredMixin, View):
    def get(self, request, pk):
        folio = get_object_or_404(
            Folio.objects
                .select_related('reservation__primary_guest',
                                'reservation__property')
                .prefetch_related('charges', 'payments'),
            pk=pk,
        )
        pdf = render_folio_invoice(folio)
        filename = f'folio-{folio.reservation.reservation_number}.pdf'
        inline = request.GET.get('download') != '1'
        return _pdf_response(pdf, filename, inline=inline)


class PaymentReceiptPDFView(StaffRequiredMixin, View):
    def get(self, request, pk):
        payment = get_object_or_404(
            FolioPayment.objects.select_related(
                'folio__reservation__primary_guest',
                'folio__reservation__property',
                'received_by',
            ),
            pk=pk,
        )
        pdf = render_payment_receipt(payment)
        filename = f'receipt-{payment.pk:08d}.pdf'
        inline = request.GET.get('download') != '1'
        return _pdf_response(pdf, filename, inline=inline)


class LeaseAgreementPDFView(StaffRequiredMixin, View):
    def get(self, request, pk):
        lease = get_object_or_404(
            Lease.objects.select_related(
                'tenant', 'landlord', 'unit', 'unit__property',
            ),
            pk=pk,
        )
        pdf = render_lease_agreement(lease)
        filename = f'lease-{lease.lease_number}.pdf'
        inline = request.GET.get('download') != '1'
        return _pdf_response(pdf, filename, inline=inline)
'@


New-PyFile -Path 'apps/core/documents/pdf/urls.py' -Content @'
from django.urls import path
from . import views

app_name = 'pdf'

urlpatterns = [
    path('folio/<int:pk>/', views.FolioInvoicePDFView.as_view(),
         name='folio_invoice'),
    path('receipt/<int:pk>/', views.PaymentReceiptPDFView.as_view(),
         name='payment_receipt'),
    path('lease/<int:pk>/', views.LeaseAgreementPDFView.as_view(),
         name='lease_agreement'),
]
'@


New-PyFile -Path 'apps/core/documents/pdf/tasks.py' -Content @'
"""Celery tasks for bulk PDF generation."""
import logging

from celery import shared_task
from django_tenants.utils import schema_context

from apps.shared.tenants.models import Tenant

logger = logging.getLogger(__name__)


@shared_task
def generate_monthly_statements_for_all_tenants():
    tenants = Tenant.objects.filter(is_active=True).exclude(
        schema_name='public',
    )
    total = 0

    for tenant in tenants:
        with schema_context(tenant.schema_name):
            try:
                from apps.core.properties.models import Property
                from .statements import render_landlord_statement
                from django.utils import timezone
                from datetime import timedelta

                last_month_end = (
                    timezone.now().date().replace(day=1)
                    - timedelta(days=1)
                )
                last_month_start = last_month_end.replace(day=1)

                for prop in Property.objects.filter(status='ACTIVE'):
                    try:
                        render_landlord_statement(
                            prop, last_month_start, last_month_end,
                        )
                        total += 1
                    except Exception as exc:
                        logger.exception(
                            f'Statement failed for {prop.name}: {exc}'
                        )
            except Exception as exc:
                logger.exception(
                    f'Statements failed for tenant '
                    f'{tenant.schema_name}: {exc}'
                )

    return f'Generated {total} landlord statements'
'@


# ---- Tests ----
Write-Host ''
Write-Host 'Writing tests...' -ForegroundColor Cyan

New-PyFile -Path 'tests/test_pdf/__init__.py' -Content ''

New-PyFile -Path 'tests/test_pdf/test_generation.py' -Content @'
import pytest
from apps.core.documents.pdf.receipt import render_payment_receipt
from apps.core.documents.pdf.folio import render_folio_invoice
from apps.core.documents.pdf.lease import render_lease_agreement


@pytest.mark.django_db(transaction=True)
class TestFolioPDF:
    def test_folio_pdf_renders(self, folio):
        pdf = render_folio_invoice(folio)
        assert pdf[:4] == b'%PDF'
        assert len(pdf) > 2000


@pytest.mark.django_db(transaction=True)
class TestReceiptPDF:
    def test_receipt_pdf_renders(self, folio_payment):
        pdf = render_payment_receipt(folio_payment)
        assert pdf[:4] == b'%PDF'


@pytest.mark.django_db(transaction=True)
class TestLeasePDF:
    def test_lease_pdf_renders(self, lease):
        pdf = render_lease_agreement(lease)
        assert pdf[:4] == b'%PDF'
        assert len(pdf) > 5000
'@


# ---- requirements.txt / .gitignore ----
Write-Host ''
Write-Host 'Updating config files...' -ForegroundColor Cyan

Add-BlockOnce `
    -Path 'requirements.txt' `
    -Marker 'reportlab>=4.2' `
    -Block "`n# PDF generation`nreportlab>=4.2`nqrcode[pil]>=7.4`n"

Add-BlockOnce `
    -Path '.gitignore' `
    -Marker 'apps/core/documents/pdf/fonts/*.ttf' `
    -Block "`n# DejaVu PDF fonts`n*.ttf`n!apps/core/documents/pdf/fonts/*.ttf`n"


# ---- Merge urls.py ----
Write-Host ''
Write-Host 'Wiring PDF URLs into config/urls.py...' -ForegroundColor Cyan

Merge-UrlInclude -Path 'config/urls.py'


# ---- Done ----
Write-Host ''
Write-Host '========================================================' -ForegroundColor Green
Write-Host ' PDF modules installed.' -ForegroundColor Green
Write-Host '========================================================' -ForegroundColor Green
Write-Host ''
Write-Host 'Next steps:'
Write-Host '  1. Download DejaVu fonts (see:'
Write-Host '     https://github.com/dejavu-fonts/dejavu-fonts/releases)'
Write-Host '     Copy the 4 .ttf files into:'
Write-Host '       apps\core\documents\pdf\fonts\'
Write-Host ''
Write-Host '  2. pip install -r requirements.txt'
Write-Host ''
Write-Host '  3. pytest tests\test_pdf\ -v'
Write-Host ''