from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from apps.core.models import TimeStampedModel


class Document(TimeStampedModel):
    """A file attached to any entity via GenericForeignKey."""

    class DocType(models.TextChoices):
        LEASE_AGREEMENT = 'LEASE', 'Lease Agreement'
        SALE_AGREEMENT = 'SALE', 'Sale Agreement'
        ID_DOCUMENT = 'ID', 'Identity Document'
        INVOICE = 'INV', 'Invoice'
        PROPERTY_PHOTO = 'PHOTO', 'Property Photo'
        MAINTENANCE_REPORT = 'MAINT', 'Maintenance Report'
        OTHER = 'OTHER', 'Other'

    doc_type = models.CharField(max_length=10, choices=DocType.choices)
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='documents/%Y/%m/')
    file_size = models.PositiveIntegerField(help_text='Size in bytes')
    mime_type = models.CharField(max_length=100, blank=True)
    uploaded_by = models.ForeignKey(
        'shared_users.User', on_delete=models.SET_NULL, null=True,
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    expiry_date = models.DateField(
        null=True, blank=True,
        help_text='Optional expiry date for time-limited documents',
    )
    is_current = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['doc_type', 'is_current']),
        ]

    def __str__(self):
        return f'{self.title} ({self.get_doc_type_display()})'