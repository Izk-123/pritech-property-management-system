"""
ReportLab PDF for subscription invoices.

The invoice is generated with the same base infrastructure as the
tenant-facing PDFs (apps/core/documents/pdf/base.py) but with a
different layout — the "customer" is the tenant, and the "vendor"
is Pritech PMS.

If the platform is itself VAT-registered, the invoice includes an
MRA EIS block. Otherwise it's a plain commercial invoice.
"""
from datetime import datetime
from io import BytesIO

import qrcode
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image, Paragraph, Spacer, Table, TableStyle,
)

# Reuse the tenant PDF base
from apps.core.documents.pdf.base import (
    COLOR_BG_SOFT, COLOR_BORDER, COLOR_DANGER, COLOR_INK, COLOR_MUTED,
    COLOR_PRIMARY, COLOR_PRIMARY_DK, COLOR_SUCCESS,
    build_pdf, get_styles,
)


# ─────────────────────────────────────────────────────────────────────
# Platform-level branding (not per-tenant — the vendor is Pritech)
# ─────────────────────────────────────────────────────────────────────

PLATFORM_VENDOR = {
    'name': 'Pritech',
    'legal_name': 'Pritech Limited',
    'address': 'Lilongwe, Malawi',
    'phone': '+265 99 123 4567',
    'email': 'billing@pritechmw.com',
    'website': 'pms.pritechmw.com',
    'tin': '',              # Populate once registered
    'vat_number': '',       # Populate once VAT-registered
}


def _qr_image(data, size_mm=25):
    """Generate a ReportLab Image flowable containing a QR code."""
    if not data:
        return None
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
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


# ─────────────────────────────────────────────────────────────────────
# The renderer
# ─────────────────────────────────────────────────────────────────────

def render_subscription_invoice(invoice):
    """
    Render a SubscriptionInvoice to PDF bytes.

    Args:
        invoice: apps.shared.billing.models.SubscriptionInvoice instance
                 with prefetched payments.

    Returns:
        bytes
    """
    styles = get_styles()
    subscription = invoice.subscription
    tenant = invoice.tenant
    plan = invoice.plan

    story = []

    # ── Vendor header (Pritech) ────────────────────────────
    story.append(Paragraph('Invoice', styles['title']))
    story.append(Paragraph(
        f'<b>{invoice.invoice_number}</b>',
        styles['subtitle'],
    ))
    story.append(Spacer(1, 6 * mm))

    # ── Bill-to and invoice-details table ──────────────────
    billed_to = [
        Paragraph('BILLED TO', styles['label']),
        Paragraph(f'<b>{tenant.name}</b>', styles['value']),
    ]
    if tenant.contact_email:
        billed_to.append(Paragraph(tenant.contact_email, styles['body_small']))
    if tenant.contact_phone:
        billed_to.append(Paragraph(tenant.contact_phone, styles['body_small']))
    billed_to.append(Paragraph(
        f'Workspace: {tenant.schema_name}',
        styles['body_small'],
    ))

    invoice_details = [
        Paragraph('INVOICE DETAILS', styles['label']),
        Paragraph(
            f'<b>Issued:</b> {invoice.issue_date:%d %b %Y}',
            styles['value'],
        ),
        Paragraph(
            f'<b>Due:</b> {invoice.due_date:%d %b %Y}',
            styles['value'],
        ),
        Paragraph(
            f'<b>Period:</b> {invoice.period_start:%d %b %Y} — '
            f'{invoice.period_end:%d %b %Y}',
            styles['body_small'],
        ),
    ]
    if invoice.paid_date:
        invoice_details.append(Paragraph(
            f'<b>Paid:</b> {invoice.paid_date:%d %b %Y}',
            styles['body_small'],
        ))

    header_table = Table(
        [[billed_to, invoice_details]],
        colWidths=[95 * mm, 75 * mm],
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

    # ── Line items ────────────────────────────────────────
    line_rows = [[
        Paragraph('<b>DESCRIPTION</b>', styles['label']),
        Paragraph('<b>PERIOD</b>', styles['label']),
        Paragraph('<b>AMOUNT</b>', styles['label']),
    ]]
    line_rows.append([
        Paragraph(
            f'{plan.name} — {plan.get_interval_display()} subscription',
            styles['body'],
        ),
        Paragraph(
            f'{invoice.period_start:%d %b} → {invoice.period_end:%d %b %Y}',
            styles['body_small'],
        ),
        Paragraph(
            _money(invoice.amount, invoice.currency),
            styles['right'],
        ),
    ])

    line_table = Table(
        line_rows,
        colWidths=[95 * mm, 40 * mm, 35 * mm],
        repeatRows=1,
    )
    line_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COLOR_BG_SOFT),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, COLOR_BORDER),
        ('LINEBELOW', (0, 1), (-1, -2), 0.25, COLOR_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3 * mm),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3 * mm),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5 * mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5 * mm),
    ]))
    story.append(line_table)
    story.append(Spacer(1, 8 * mm))

    # ── Summary ───────────────────────────────────────────
    is_paid = invoice.status == 'PAID'
    total_label = 'TOTAL PAID' if is_paid else 'TOTAL DUE'
    total_colour = COLOR_SUCCESS if is_paid else (
        COLOR_DANGER if invoice.is_overdue else COLOR_PRIMARY_DK
    )

    summary_data = [
        [Paragraph('<b>SUBTOTAL</b>', styles['label']),
         Paragraph(_money(invoice.amount, invoice.currency),
                   styles['right'])],
    ]

    if PLATFORM_VENDOR.get('vat_number'):
        vat_rate = 16.5  # Malawi VAT
        vat_amount = invoice.amount * vat_rate / 100
        summary_data.append([
            Paragraph(f'<b>VAT ({vat_rate}%)</b>', styles['label']),
            Paragraph(_money(vat_amount, invoice.currency),
                      styles['right']),
        ])

    summary_data.append([
        Paragraph(f'<b>{total_label}</b>', styles['label']),
        Paragraph(
            f'<font color="{total_colour.hexval()}">'
            f'<b>{_money(invoice.amount, invoice.currency)}</b></font>',
            styles['right_bold'],
        ),
    ])

    summary_table = Table(
        summary_data,
        colWidths=[120 * mm, 50 * mm],
        hAlign='RIGHT',
    )
    summary_table.setStyle(TableStyle([
        ('LINEABOVE', (0, len(summary_data) - 1),
         (-1, len(summary_data) - 1), 0.75, COLOR_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 2 * mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2 * mm),
        ('LEFTPADDING', (0, 0), (-1, -1), 3 * mm),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3 * mm),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 10 * mm))

    # ── Payment history (if paid) ─────────────────────────
    payments = invoice.payments.all()
    if payments.exists():
        story.append(Paragraph('Payments Received', styles['h2']))
        pay_rows = [[
            Paragraph('<b>DATE</b>', styles['label']),
            Paragraph('<b>METHOD</b>', styles['label']),
            Paragraph('<b>REFERENCE</b>', styles['label']),
            Paragraph('<b>AMOUNT</b>', styles['label']),
        ]]
        for p in payments:
            pay_rows.append([
                Paragraph(f'{p.received_at:%d %b %Y}', styles['body_small']),
                Paragraph(p.get_method_display(), styles['body_small']),
                Paragraph(p.reference or '—', styles['body_small']),
                Paragraph(_money(p.amount, p.currency), styles['right']),
            ])

        pay_table = Table(
            pay_rows,
            colWidths=[30 * mm, 45 * mm, 60 * mm, 35 * mm],
            repeatRows=1,
        )
        pay_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COLOR_BG_SOFT),
            ('LINEBELOW', (0, 0), (-1, 0), 0.5, COLOR_BORDER),
            ('LINEBELOW', (0, 1), (-1, -2), 0.25, COLOR_BORDER),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 3 * mm),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3 * mm),
            ('TOPPADDING', (0, 0), (-1, -1), 2 * mm),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2 * mm),
        ]))
        story.append(pay_table)
        story.append(Spacer(1, 8 * mm))

    # ── Payment instructions (if unpaid) ──────────────────
    if not is_paid:
        instructions = [
            Paragraph('How to Pay', styles['h2']),
            Paragraph(
                'Pay online via PayChangu using Airtel Money, TNM Mpamba, '
                'or card. Log in to your workspace and visit '
                '<b>Billing</b> to initiate the payment.',
                styles['body'],
            ),
            Spacer(1, 4 * mm),
            Paragraph(
                f'<b>Reference:</b> {invoice.invoice_number}',
                styles['value'],
            ),
            Paragraph(
                f'<b>Amount:</b> {_money(invoice.amount, invoice.currency)}',
                styles['value'],
            ),
            Paragraph(
                f'<b>Due:</b> {invoice.due_date:%d %B %Y}',
                styles['value'],
            ),
        ]
        if invoice.is_overdue:
            instructions.append(Spacer(1, 3 * mm))
            instructions.append(Paragraph(
                f'<font color="{COLOR_DANGER.hexval()}">'
                f'<b>This invoice is {invoice.days_overdue} days overdue.</b>'
                f'</font>',
                styles['body'],
            ))

        box = Table([[instructions]], colWidths=[170 * mm])
        box.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), COLOR_BG_SOFT),
            ('BOX', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ('LEFTPADDING', (0, 0), (-1, -1), 4 * mm),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4 * mm),
            ('TOPPADDING', (0, 0), (-1, -1), 4 * mm),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4 * mm),
        ]))
        story.append(box)
        story.append(Spacer(1, 8 * mm))

    # ── MRA EIS QR block (if applicable) ──────────────────
    if invoice.mra_invoice_number:
        qr = _qr_image(invoice.mra_invoice_number, size_mm=26)
        mra_block = [
            Paragraph('MALAWI REVENUE AUTHORITY', styles['label']),
            Paragraph(
                f'<b>Invoice No:</b> {invoice.mra_invoice_number}',
                styles['value'],
            ),
            Paragraph(
                'Scan the QR code to verify this invoice on the MRA '
                'Electronic Invoicing System.',
                styles['body_small'],
            ),
        ]
        if qr:
            mra_block.append(Spacer(1, 2 * mm))
            mra_block.append(qr)

        mra_box = Table([[mra_block]], colWidths=[170 * mm])
        mra_box.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), COLOR_BG_SOFT),
            ('BOX', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ('LEFTPADDING', (0, 0), (-1, -1), 4 * mm),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4 * mm),
            ('TOPPADDING', (0, 0), (-1, -1), 3 * mm),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3 * mm),
        ]))
        story.append(mra_box)
        story.append(Spacer(1, 6 * mm))

    # ── Legal footer ──────────────────────────────────────
    story.append(Paragraph(
        f'{PLATFORM_VENDOR["legal_name"]} · '
        f'{PLATFORM_VENDOR["address"]} · '
        f'{PLATFORM_VENDOR["email"]}',
        styles['legal'],
    ))
    if PLATFORM_VENDOR.get('tin'):
        story.append(Paragraph(
            f'TIN: {PLATFORM_VENDOR["tin"]}'
            + (f'  ·  VAT: {PLATFORM_VENDOR["vat_number"]}'
               if PLATFORM_VENDOR.get('vat_number') else ''),
            styles['legal'],
        ))
    story.append(Paragraph(
        'Thank you for using Pritech PMS.',
        styles['legal'],
    ))

    # ── Build ─────────────────────────────────────────────
    return build_pdf(
        story,
        title='Subscription Invoice',
        subject=f'Invoice {invoice.invoice_number}',
        author=PLATFORM_VENDOR['legal_name'],
    )