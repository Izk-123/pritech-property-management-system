# apps/hospitality/reservations/views.py
"""
Reservation views.

Front desk, reservation detail, and the create / edit / check-in
flows. The create and edit views are the entry point for the
overbooking fix — they take a unit from the form and create the
ReservationRoom immediately, so confirmed bookings block the room
from that moment on.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, FormView, View,
)

from apps.core.mixins import TenantStaffRequiredMixin

from .forms import ReservationForm, CheckInForm
from .models import Reservation
from .services import (
    attach_unit_to_reservation,
    cancel_reservation,
    check_in_reservation,
    check_out_reservation,
    CheckInError,
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
                Q(reservation_number__icontains=search) |
                Q(primary_guest__full_name__icontains=search) |
                Q(primary_guest__phone_primary__icontains=search)
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
    """
    Create a reservation and immediately assign a room.

    The form's ``unit`` field carries the room. ``attach_unit_to_reservation``
    locks the unit row, re-checks for conflicts under the lock, and
    creates the ReservationRoom. This is where the overbooking fix
    lives — the room is held from this moment on.
    """
    model = Reservation
    form_class = ReservationForm
    template_name = 'pages/hospitality/reservation_form.html'

    @transaction.atomic
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.status = Reservation.Status.CONFIRMED

        # Save the reservation first — we need its PK to create the
        # ReservationRoom.
        self.object = form.save()

        try:
            attach_unit_to_reservation(
                reservation=self.object,
                unit=form.cleaned_data['unit'],
                rate_per_night=form.cleaned_data['rate_per_night'],
            )
        except Exception as exc:
            # attach_unit_to_reservation raised — probably a conflict
            # discovered under the lock. Delete the reservation we
            # just created so the transaction is clean, then surface
            # the error on the form. The outer atomic() rolls back
            # everything if we raise; deleting explicitly lets us
            # fall into the "form_invalid" path with a nice message.
            self.object.delete()
            form.add_error('unit', str(exc))
            return self.form_invalid(form)

        messages.success(
            self.request,
            f'Reservation {self.object.reservation_number} created. '
            f'Room {form.cleaned_data["unit"].identifier} held.',
        )
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse_lazy('reservations:detail', kwargs={'pk': self.object.pk})


class ReservationUpdateView(LoginRequiredMixin, UpdateView):
    """
    Edit an existing reservation.

    If the room changed, the old ReservationRoom is replaced. The
    new assignment is re-checked under a lock, exactly like create.
    """
    model = Reservation
    form_class = ReservationForm
    template_name = 'pages/hospitality/reservation_form.html'

    def get_queryset(self):
        # Only editable before check-in.
        return Reservation.objects.exclude(
            status__in=[
                Reservation.Status.CHECKED_IN,
                Reservation.Status.CHECKED_OUT,
                Reservation.Status.CANCELLED,
            ]
        )

    @transaction.atomic
    def form_valid(self, form):
        self.object = form.save()

        new_unit = form.cleaned_data['unit']
        new_rate = form.cleaned_data['rate_per_night']

        # Was this unit previously assigned? If the room is unchanged
        # we skip the conflict check — the room is already held by
        # this reservation and re-validating it would self-conflict.
        existing = self.object.rooms.filter(unit=new_unit).first()
        if existing and existing.rate_per_night == new_rate:
            messages.success(self.request, 'Reservation updated.')
            return redirect(self.get_success_url())

        # Room or rate changed. Replace the assignment under a lock.
        try:
            self.object.rooms.exclude(unit=new_unit).delete()
            attach_unit_to_reservation(
                reservation=self.object,
                unit=new_unit,
                rate_per_night=new_rate,
            )
        except Exception as exc:
            form.add_error('unit', str(exc))
            return self.form_invalid(form)

        messages.success(self.request, 'Reservation updated.')
        return redirect(self.get_success_url())

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
            Reservation.objects
                .select_related('primary_guest', 'property')
                .prefetch_related('rooms__unit'),
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
        return (
            Reservation.objects
            .filter(
                status=Reservation.Status.CONFIRMED,
                check_in=today,
            )
            .select_related('primary_guest', 'property')
            .prefetch_related('rooms__unit')
            .order_by('primary_guest__full_name')
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.now().date()

        ctx['departures'] = (
            Reservation.objects
            .filter(
                status=Reservation.Status.CHECKED_IN,
                check_out=today,
            )
            .select_related('primary_guest', 'property')
            .prefetch_related('rooms__unit', 'folio')
            .order_by('primary_guest__full_name')
        )

        ctx['in_house'] = (
            Reservation.objects
            .filter(
                status=Reservation.Status.CHECKED_IN,
                check_in__lte=today,
                check_out__gt=today,
            )
            .select_related('primary_guest', 'property')
            .prefetch_related('rooms__unit', 'folio')
            .order_by('primary_guest__full_name')
        )

        return ctx