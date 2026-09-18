from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Document


@admin.register(Document)
class DocumentAdmin(ModelAdmin):
    list_display = ('title', 'doc_type', 'content_type', 'object_id',
                    'is_current', 'created_at')
    list_filter = ('doc_type', 'is_current', 'content_type')
    search_fields = ('title', 'notes')
    readonly_fields = ('file_size', 'mime_type', 'content_type', 'object_id')