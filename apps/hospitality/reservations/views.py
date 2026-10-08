# apps/hospitality/reservations/views.py
"""
Reservation views.

Front desk, reservation detail, and the create / edit / check-in
flows. The create and edit views are the entry point for the
overbooking fix — they take a unit from the form and create the
ReservationRoom immediately, so confirmed bookings block the room
from that moment on.

The create flow also fires the guest-portal WhatsApp message (see
``ReservationCreateView.form_valid``). The send is best-effort,
asynchronous, and queued with ``transaction.on_commit`` so a rolled-
back booking never produces a stray message.

Two guest-facing portals exist:
  • ``GuestPortalView`` (this module, ``reservations:guest_portal``)
    — the original in-reservations view. Still mounted for
    backwards compatibility; new links should not point here.
  • ``apps.hospitality.guest_portal`` (``/stay/<token>/``)
    — the current landing page, targeted by the WhatsApp task.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.http import Http404
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
    """
    Paginated reservation list with optional status filter and
    free-text search on reservation number, guest name, or phone.
    """
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
    """
    Full reservation view: guest, rooms, folio charges, and payments
    are all prefetched so the template renders without extra queries.
    """
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

    After the transaction commits, the guest-portal WhatsApp link is
    queued. See ``form_valid`` for the exact sequencing and why it
    matters.
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

        # ── Queue the guest-portal WhatsApp link ───────────────────
        #
        # Three failure modes we deliberately tolerate:
        #
        #   1. The guest_portal app isn't installed (fresh checkout,
        #      feature rolled back on a branch). ImportError is
        #      swallowed, the booking still succeeds.
        #
        #   2. The Celery broker is unreachable. The `.delay()` call
        #      raises inside the on_commit callback — but the callback
        #      runs *after* the DB commit, so the reservation is
        #      already durable. We swallow it and move on.
        #
        #   3. The guest has no phone number on file. The task itself
        #      returns 'no-phone' without raising. Nothing to catch
        #      here.
        #
        # Why `transaction.on_commit`?
        #
        # form_valid is decorated with @transaction.atomic. If any
        # downstream signal raises *after* we queue the task, the
        # whole transaction rolls back — but the Celery worker may
        # already have picked up the message and be about to send it.
        # The guest would receive a link to a reservation that never
        # existed. on_commit defers the .delay() call until after the
        # outer transaction has actually committed, so a rollback
        # produces no message.
        #
        # The task itself lazily generates `guest_access_token` if the
        # reservation doesn't have one — the field is nullable on the
        # model and nothing else in the flow populates it.
        try:
            from apps.hospitality.guest_portal.tasks import (
                send_guest_portal_link,
            )
            reservation_pk = self.object.pk

            def _queue_guest_link():
                try:
                    send_guest_portal_link.delay(reservation_pk)
                except Exception:
                    # Broker down, task unregistered, etc. The
                    # booking has already committed — swallow so the
                    # request completes cleanly. The link can be
                    # re-sent manually from the reservation detail
                    # page if the guest asks.
                    pass

            transaction.on_commit(_queue_guest_link)
        except ImportError:
            # guest_portal app not installed — nothing to queue.
            pass

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
    """
    Cancel a reservation. Delegates to services.cancel_reservation,
    which deletes the ReservationRoom rows (freeing inventory) and
    flips status to CANCELLED.
    """
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


# ─── Legacy guest portal ──────────────────────────────────────────
#
# This view predates apps.hospitality.guest_portal. It's still
# mounted at `/reservations/guest/<token>/` and is referenced by
# Reservation.guest_portal_url, so we keep it working for links
# that have already been shared. New links point at the guest_portal
# app's `/stay/<token>/` route instead.
#
# The GuestPortalMixin in the new app validates the token more
# cleanly (single get_object_or_404, expiry handled by the model
# property). This class duplicates that logic with a slightly
# different code path — do not extend it, do not add features to it.

class GuestPortalView(DetailView):
    """Anonymous reservation-scoped guest portal (legacy path)."""
    model = Reservation
    template_name = 'pages/hospitality/guest_portal.html'
    context_object_name = 'reservation'
    slug_field = 'guest_access_token'
    slug_url_kwarg = 'token'

    def get_queryset(self):
        return Reservation.objects.select_related(
            'primary_guest', 'property', 'folio', 'rate_plan'
        ).prefetch_related('rooms__unit', 'folio__charges', 'folio__payments')

    def dispatch(self, request, *args, **kwargs):
        token = kwargs.get('token')
        if not token:
            raise Http404

        reservation = self.get_object()
        if reservation is None or not reservation.guest_access_is_valid:
            raise Http404

        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        queryset = queryset or self.get_queryset()
        token = self.kwargs.get(self.slug_url_kwarg)
        if token is None:
            raise Http404
        try:
            return queryset.get(guest_access_token=token)
        except queryset.model.DoesNotExist:
            raise Http404


# ─── Check-In ─────────────────────────────────────────────────────

class CheckInView(LoginRequiredMixin, FormView):
    """
    Assign one or more available units and flip the reservation to
    CHECKED_IN. Inventory conflicts are enforced by the service
    layer, not the form — the form only offers rooms that are free.
    """
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
    """
    Render the check-out confirmation page on GET, perform the check-
    out on POST. The service layer enforces a zero folio balance.
    """
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
    """
    The staff landing page: today's arrivals, today's departures,
    and everyone currently in-house. Each block is its own queryset
    so the template can render them independently.
    """
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