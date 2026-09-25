# apps/core/models.py
from django.db import models
from PIL import Image
from io import BytesIO
from django.core.files.base import ContentFile
from apps.core.properties.models import Property


class OptimizedImageMixin:
    """Add WebP conversion to models with ImageField."""

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.image:
            img = Image.open(self.image.path)
            if img.width > 1920 or img.height > 1920:
                img.thumbnail((1920, 1920), Image.LANCZOS)
                img.save(self.image.path, quality=85, optimize=True)


# Usage in PropertyImage model
class PropertyImage(OptimizedImageMixin, models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE)
    image = models.ImageField(upload_to='properties/%Y/%m/')


class TimeStampedModel(models.Model):
    """Abstract base model with created and updated timestamps."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
