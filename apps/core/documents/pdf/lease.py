"""
Lease agreement — generates a complete, signable PDF for a rental
lease. Uses `PageBreak()` to split the document into sections:

    1. Parties and property
    2. Term, rent, and deposit
    3. Obligations and rules
    4. Signatures
"""
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak, Paragraph, Spacer, Table, TableStyle,
)

from .base import (
    COLOR_BG_SOFT, COLOR_BORDER, COLOR_MUTED,
    build_pdf, get_styles, get_tenant_branding,
)


def _kv_table(rows, styles):
    """Build a simple key/value table for lease terms."""
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
    """Render a full lease agreement PDF."""
    styles = get_styles()
    branding = get_tenant_branding()

    story = []

    # ── Section 1 — Parties and Property ─────────────────────────
    story.append(Paragraph('Residential Tenancy Agreement', styles['title']))
    story.append(Paragraph(
        f'Lease <b>{lease.lease_number}</b>',
        styles['subtitle'],
    ))
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
         (landlord.phone_primary if landlord else branding.get('phone', '')) or '—'),
        ('TENANT', lease.tenant.full_name),
        ('TENANT CONTACT', lease.tenant.phone_primary or '—'),
        ('PROPERTY', lease.unit.property.name),
        ('UNIT', lease.unit.identifier),
        ('PROPERTY ADDRESS', lease.unit.property.address or '—'),
    ], styles))

    story.append(PageBreak())

    # ── Section 2 — Term, Rent, Deposit ──────────────────────────
    story.append(Paragraph('2. Term, Rent, and Deposit', styles['h1']))

    story.append(_kv_table([
        ('LEASE START', lease.start_date.strftime('%d %B %Y')),
        ('LEASE END', lease.end_date.strftime('%d %B %Y')),
        ('RENT AMOUNT',
         f'{lease.rent_currency} {lease.rent_amount:,.2f}'),
        ('PAYMENT FREQUENCY', lease.get_payment_frequency_display()),
        ('RENT DUE ON', f'Day {lease.payment_due_day} of each period'),
        ('ESCALATION',
         f'{lease.escalation_percent:.1f}% annually'
         if lease.escalation_percent else 'None'),
        ('SECURITY DEPOSIT',
         f'{lease.rent_currency} {lease.deposit_amount:,.2f}'),
        ('GRACE PERIOD', f'{lease.grace_period_days} days'),
        ('LATE FEE',
         f'{lease.late_fee_percent:.1f}% or '
         f'{lease.rent_currency} {lease.late_fee_fixed:,.2f}'
         if (lease.late_fee_percent or lease.late_fee_fixed)
         else 'None'),
    ], styles))

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph('2.1 Rent Payment', styles['h2']))
    story.append(Paragraph(
        f'The Tenant shall pay rent of '
        f'{lease.rent_currency} {lease.rent_amount:,.2f} on or before '
        f'day {lease.payment_due_day} of each '
        f'{lease.get_payment_frequency_display().lower()} period. '
        f'Payment may be made by bank transfer, mobile money, or cash '
        f'as agreed between the parties.',
        styles['body'],
    ))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph('2.2 Security Deposit', styles['h2']))
    story.append(Paragraph(
        f'The Tenant shall pay a security deposit of '
        f'{lease.rent_currency} {lease.deposit_amount:,.2f} prior to '
        f'occupation. The deposit shall be refunded within 30 days of '
        f'vacation, less any deductions for damage beyond normal wear '
        f'and tear, unpaid rent, or unpaid utilities.',
        styles['body'],
    ))

    story.append(PageBreak())

    # ── Section 3 — Obligations ──────────────────────────────────
    story.append(Paragraph('3. Obligations of the Parties', styles['h1']))

    story.append(Paragraph('3.1 The Landlord agrees to:', styles['h2']))
    for line in [
        'Deliver the property in a clean and habitable condition.',
        'Maintain the structure, roof, and exterior of the property.',
        'Ensure water and electricity connections are functioning at handover.',
        'Provide at least 24 hours notice before entering the property, '
        'except in an emergency.',
        'Refund the security deposit within 30 days of vacation, less '
        'legitimate deductions.',
    ]:
        story.append(Paragraph(f'• {line}', styles['body']))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph('3.2 The Tenant agrees to:', styles['h2']))
    for line in [
        'Pay rent on time, in full, using the agreed method.',
        'Pay for water, electricity, and any other utilities consumed.',
        'Keep the property clean and in good condition.',
        'Not sublet the property or any part of it without written consent.',
        'Not make alterations to the property without written consent.',
        'Report any damage or maintenance issue promptly to the Landlord.',
        'Return the property in the same condition as received, '
        'normal wear and tear excepted.',
    ]:
        story.append(Paragraph(f'• {line}', styles['body']))

    story.append(PageBreak())

    # ── Section 4 — Signatures ───────────────────────────────────
    story.append(Paragraph('4. Signatures', styles['h1']))
    story.append(Paragraph(
        'By signing below, both parties agree to the terms set out in '
        'this agreement.',
        styles['body'],
    ))
    story.append(Spacer(1, 10 * mm))

    signature_data = [
        [
            Paragraph('<b>LANDLORD</b>', styles['label']),
            Paragraph('<b>TENANT</b>', styles['label']),
        ],
        [
            Paragraph(
                f'{landlord.full_name if landlord else branding["name"]}',
                styles['value'],
            ),
            Paragraph(lease.tenant.full_name, styles['value']),
        ],
        ['', ''],
        [
            Paragraph('Signature: _____________________', styles['body']),
            Paragraph('Signature: _____________________', styles['body']),
        ],
        [
            Paragraph('Date: _____________________', styles['body']),
            Paragraph('Date: _____________________', styles['body']),
        ],
    ]

    signature_table = Table(
        signature_data,
        colWidths=[85 * mm, 85 * mm],
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
        f'Lease reference {lease.lease_number} · '
        f'Generated by Pritech PMS on behalf of {branding["name"]}.',
        styles['legal'],
    ))

    return build_pdf(
        story,
        title='Lease Agreement',
        subject=f'Lease {lease.lease_number}',
    )