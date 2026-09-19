from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, FormView, View,
)
from .models import Reservation
from .forms import ReservationForm, CheckInForm
from .services import (
    check_in_reservation, check_out_reservation,
    cancel_reservation, CheckInError,
)


# ─── List ──────────────────────────────────────────────────────────

class ReservationListView(LoginRequiredMixin, ListView):
    model = Reservation
    template_name = 'pages/hospitality/reservation_list.html'
    context_object_name = 'reservations'
    paginate_by = 25

    def get_queryset(self):
        qs = Reservation.objects.select_related(
            'primary_guest', 'property'
        ).order_by('-check_in')

        status = self.request.GET.get('status', '')
        if status in Reservation.Status.values:
            qs = qs.filter(status=status)

        search = self.request.GET.get('q', '').strip()
        if search:
            qs = qs.filter(
                models.Q(reservation_number__icontains=search) |
                models.Q(primary_guest__full_name__icontains=search) |
                models.Q(primary_guest__phone_primary__icontains=search)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['statuses'] = Reservation.Status.choices
        ctx['current_status'] = self.request.GET.get('status', '')
        ctx['search_query'] = self.request.GET.get('q', '')
        return ctx


# ─── Detail ────────────────────────────────────────────────────────

class ReservationDetailView(LoginRequiredMixin, DetailView):
    model = Reservation
    template_name = 'pages/hospitality/reservation_detail.html'
    context_object_name = 'reservation'

    def get_queryset(self):
        return Reservation.objects.select_related(
            'primary_guest', 'property', 'rate_plan'
        ).prefetch_related(
            'rooms__unit',
            'folio__charges',
            'folio__payments',
        )


# ─── Create / Edit ────────────────────────────────────────────────

class ReservationCreateView(LoginRequiredMixin, CreateView):
    model = Reservation
    form_class = ReservationForm
    template_name = 'pages/hospitality/reservation_form.html'

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.status = Reservation.Status.CONFIRMED
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Reservation {self.object.reservation_number} created.',
        )
        return response

    def get_success_url(self):
        return reverse_lazy('reservations:detail', kwargs={'pk': self.object.pk})


class ReservationUpdateView(LoginRequiredMixin, UpdateView):
    model = Reservation
    form_class = ReservationForm
    template_name = 'pages/hospitality/reservation_form.html'

    def get_queryset(self):
        # Only allow editing reservations that haven't checked in or out
        return Reservation.objects.exclude(
            status__in=[
                Reservation.Status.CHECKED_IN,
                Reservation.Status.CHECKED_OUT,
                Reservation.Status.CANCELLED,
            ]
        )

    def form_valid(self, form):
        messages.success(self.request, 'Reservation updated.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('reservations:detail', kwargs={'pk': self.object.pk})


# ─── Cancel ───────────────────────────────────────────────────────

class ReservationCancelView(LoginRequiredMixin, View):
    def post(self, request, pk):
        reservation = get_object_or_404(Reservation, pk=pk)
        reason = request.POST.get('reason', '').strip()
        try:
            cancel_reservation(reservation, reason=reason, user=request.user)
            messages.success(
                request,
                f'Reservation {reservation.reservation_number} cancelled.',
            )
        except CheckInError as e:
            messages.error(request, str(e))
        return redirect('reservations:detail', pk=pk)


# ─── Check-In ─────────────────────────────────────────────────────

class CheckInView(LoginRequiredMixin, FormView):
    template_name = 'pages/hospitality/check_in.html'
    form_class = CheckInForm

    def get_reservation(self):
        return get_object_or_404(
            Reservation.objects.select_related('primary_guest', 'property'),
            pk=self.kwargs['pk'],
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['reservation'] = self.get_reservation()
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['reservation'] = self.get_reservation()
        return ctx

    def form_valid(self, form):
        reservation = self.get_reservation()
        try:
            check_in_reservation(
                reservation=reservation,
                unit_assignments=form.get_unit_assignments(),
                user=self.request.user,
            )
            messages.success(
                self.request,
                f'{reservation.primary_guest.full_name} checked in.',
            )
            return redirect('reservations:detail', pk=reservation.pk)
        except CheckInError as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)


# ─── Check-Out ────────────────────────────────────────────────────

class CheckOutView(LoginRequiredMixin, DetailView):
    model = Reservation
    template_name = 'pages/hospitality/check_out.html'
    context_object_name = 'reservation'

    def get_queryset(self):
        return Reservation.objects.select_related(
            'primary_guest', 'property'
        ).prefetch_related('rooms__unit', 'folio__charges', 'folio__payments')

    def post(self, request, *args, **kwargs):
        reservation = self.get_object()
        try:
            check_out_reservation(reservation, user=request.user)
            messages.success(
                request,
                f'{reservation.primary_guest.full_name} checked out. '
                f'Housekeeping notified.',
            )
            return redirect('reservations:detail', pk=reservation.pk)
        except CheckInError as e:
            messages.error(request, str(e))
            return redirect('reservations:check_out', pk=reservation.pk)


# ─── Front Desk Dashboard ─────────────────────────────────────────

class FrontDeskDashboardView(LoginRequiredMixin, ListView):
    template_name = 'pages/hospitality/front_desk.html'
    context_object_name = 'arrivals'

    def get_queryset(self):
        today = timezone.now().date()
        return Reservation.objects.filter(
            status=Reservation.Status.CONFIRMED,
            check_in=today,
        ).select_related('primary_guest', 'property').order_by('primary_guest__full_name')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.now().date()
        ctx['departures'] = Reservation.objects.filter(
            status=Reservation.Status.CHECKED_IN,
            check_out=today,
        ).select_related('primary_guest', 'property')
        ctx['in_house'] = Reservation.objects.filter(
            status=Reservation.Status.CHECKED_IN,
            check_in__lte=today,
            check_out__gt=today,
        ).select_related('primary_guest', 'property').prefetch_related('folio')
        return ctx