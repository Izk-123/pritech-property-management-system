"""
Staff-only views for managing Document records.

Documents are attached to other entities (Person, Property, Unit,
Lease, Invoice) through Django's GenericForeignKey.
"""
import mimetypes
from django.contrib import messages
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView
from apps.core.mixins import StaffRequiredMixin
from .models import Document
from .forms import DocumentUploadForm


class DocumentListView(StaffRequiredMixin, ListView):
    """List all documents for the current tenant."""
    model = Document
    template_name = 'pages/documents/list.html'
    context_object_name = 'documents'
    paginate_by = 30

    def get_queryset(self):
        qs = Document.objects.select_related(
            'content_type', 'uploaded_by',
        ).order_by('-created_at')

        search = self.request.GET.get('q', '').strip()
        if search:
            qs = qs.filter(
                Q(title__icontains=search) |
                Q(notes__icontains=search)
            )

        doc_type = self.request.GET.get('type', '').strip()
        if doc_type in Document.DocType.values:
            qs = qs.filter(doc_type=doc_type)

        if self.request.GET.get('current') == '1':
            qs = qs.filter(is_current=True)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['doc_types'] = Document.DocType.choices
        ctx['current_type'] = self.request.GET.get('type', '')
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['show_only_current'] = self.request.GET.get('current') == '1'
        ctx['total_documents'] = Document.objects.count()
        ctx['current_documents'] = Document.objects.filter(is_current=True).count()
        return ctx


class DocumentUploadView(StaffRequiredMixin, CreateView):
    """Upload a new document and attach it to an entity."""
    model = Document
    form_class = DocumentUploadForm
    template_name = 'pages/documents/upload.html'

    def form_valid(self, form):
        instance = form.save(commit=False)
        instance.uploaded_by = self.request.user

        # Detect file size and mime type
        uploaded_file = form.cleaned_data.get('file')
        if uploaded_file:
            instance.file_size = uploaded_file.size
            mime, _ = mimetypes.guess_type(uploaded_file.name)
            instance.mime_type = mime or ''

        instance.save()
        messages.success(
            self.request,
            f'Document "{instance.title}" uploaded successfully.',
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('documents:list')