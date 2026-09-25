# apps/core/models.py
from django.db import models
from PIL import Image


class OptimizedImageMixin:
    """Add WebP conversion to models with ImageField."""

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.image:
            img = Image.open(self.image.path)
            if img.width > 1920 or img.height > 1920:
                img.thumbnail((1920, 1920), Image.LANCZOS)
                img.save(self.image.path, quality=85, optimize=True)


class PropertyImage(OptimizedImageMixin, models.Model):
    """Image attached to a Property."""
    # String reference avoids a circular import with properties.models,
    # which itself imports TimeStampedModel from this module.
    property = models.ForeignKey(
        'properties.Property',
        on_delete=models.CASCADE,
        related_name='images',
    )
    image = models.ImageField(upload_to='properties/%Y/%m/')

    class Meta:
        verbose_name = 'property image'
        verbose_name_plural = 'property images'

    def __str__(self):
        return f'Image for {self.property}'


class TimeStampedModel(models.Model):
    """Abstract base model with created and updated timestamps."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
