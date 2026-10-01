"""
Template filters for rendering Django form fields with CSS classes.

Used by the allauth template overrides under templates/allauth/ so
allauth's built-in widgets pick up the project's Tailwind `field`
class — otherwise inputs render unstyled.
"""
from django import template

register = template.Library()


@register.filter(name='add_class')
def add_class(field, css_class):
    """Return the field's widget re-rendered with the given CSS class."""
    existing = field.field.widget.attrs.get('class', '')
    merged = (existing + ' ' + css_class).strip()
    return field.as_widget(attrs={'class': merged})


@register.filter(name='add_error_class')
def add_error_class(field, css_class='is-invalid'):
    """Add an error-state class if the field has errors."""
    if field.errors:
        return add_class(field, css_class)
    return field