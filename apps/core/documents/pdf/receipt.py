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