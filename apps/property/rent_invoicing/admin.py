from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from .models import RentInvoice, RentInvoiceLine, RentPayment


class RentInvoiceLineInline(TabularInline):
    model = RentInvoiceLine
    extra = 0
    fields = ('line_type', 'description', 'amount')


class RentPaymentInline(TabularInline):
    model = RentPayment
    extra = 0
    fields = ('method', 'amount', 'currency', 'reference')


@admin.register(RentInvoice)
class RentInvoiceAdmin(ModelAdmin):
    list_display = (
        'invoice_number', 'tenant', 'unit', 'due_date',
        'total_due', 'amount_paid', 'status',
    )
    list_filter = ('status', 'currency')
    search_fields = (
        'invoice_number', 'tenant__full_name', 'unit__identifier',
    )
    list_select_related = ('tenant', 'unit', 'lease')
    readonly_fields = ('invoice_number',)
    inlines = [RentInvoiceLineInline, RentPaymentInline]
    date_hierarchy = 'due_date'
    actions = ['recalculate_selected']

    @admin.action(description='Recalculate totals for selected invoices')
    def recalculate_selected(self, request, queryset):
        for invoice in queryset:
            invoice.recalculate_totals()
        self.message_user(request, f'Recalculated {queryset.count()} invoices.')