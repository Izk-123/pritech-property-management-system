from datetime import timedelta
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views import View
from django.views.generic import ListView
from django.db.models import Sum, Count
from .models import TourismLevyRecord


@login_required
def levy_report_view(request):
    """Monthly Tourism Levy remittance report."""
    today = timezone.now().date()
    current_month = today.replace(day=1)

    months = TourismLevyRecord.objects.dates(
        'period_month', 'month', order='DESC',
    )[:12]

    selected_month = request.GET.get('month')
    if selected_month:
        try:
            year, month = selected_month.split('-')
            filter_month = today.replace(
                year=int(year), month=int(month), day=1,
            )
        except (ValueError, AttributeError):
            filter_month = current_month
    else:
        filter_month = current_month

    records = TourismLevyRecord.objects.filter(
        period_month=filter_month,
    ).select_related('property', 'folio', 'folio__reservation',
                     'folio__reservation__primary_guest').order_by(
        'property__name', 'folio__reservation__reservation_number'
    )

    summary = records.values('property__name').annotate(
        total_levy=Sum('levy_amount'),
        total_room_charges=Sum('room_charge_amount'),
        record_count=Count('id'),
    )

    return render(request, 'pages/compliance/levy_report.html', {
        'records': records,
        'summary': summary,
        'selected_month': filter_month,
        'months': months,
        'grand_total_levy': sum(s['total_levy'] for s in summary),
    })


class LevyMarkRemittedView(LoginRequiredMixin, View):
    """Mark levy records as remitted to the Malawi Tourism Council."""

    def post(self, request, pk):
        record = get_object_or_404(TourismLevyRecord, pk=pk)
        record.is_remitted = True
        record.remitted_at = timezone.now()
        record.save(update_fields=['is_remitted', 'remitted_at', 'updated_at'])
        messages.success(request, 'Levy record marked as remitted.')
        return redirect('compliance:tourism_levy:report')


class LevyBulkMarkRemittedView(LoginRequiredMixin, View):
    """Mark all pending levy records for a month as remitted."""

    def post(self, request):
        month_str = request.POST.get('month')
        try:
            year, month = month_str.split('-')
            month_start = timezone.now().date().replace(
                year=int(year), month=int(month), day=1,
            )
        except (ValueError, AttributeError):
            messages.error(request, 'Invalid month.')
            return redirect('compliance:tourism_levy:report')

        updated = TourismLevyRecord.objects.filter(
            period_month=month_start,
            is_remitted=False,
        ).update(is_remitted=True, remitted_at=timezone.now())

        messages.success(request, f'{updated} records marked as remitted.')
        return redirect(
            f'/compliance/levy/report/?month={month_str}'
        )