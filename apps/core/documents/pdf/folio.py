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