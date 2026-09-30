"""
Wrapper URLconf for django-two-factor-auth.

Django's include() requires the included module to declare `app_name` at
module level when a namespace is used. The upstream two_factor.urls
module doesn't declare it, and exposes urlpatterns as a 2-tuple
``(list_of_patterns, app_name)`` instead of a flat list. This wrapper
unwraps it and re-exports a flat list with app_name set.

Include this module — not `two_factor.urls` — from both URLconfs:

    path('', include('config.urls_two_factor')),
"""

from django.urls import URLPattern, URLResolver

from two_factor import urls as _tf_urls


def _is_pattern(obj):
    return isinstance(obj, (URLPattern, URLResolver))


def _unwrap(raw):
    """Return a flat list of URLPattern / URLResolver instances."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        # 2-tuple form: ([patterns], 'app_name')
        if (
            isinstance(raw, tuple)
            and len(raw) == 2
            and not _is_pattern(raw[0])
            and not _is_pattern(raw[1])
        ):
            return _unwrap(raw[0])
        # Flat collection of patterns
        return [el for el in raw if _is_pattern(el)]
    raise TypeError(
        f"Unexpected urlpatterns shape from two_factor: {type(raw).__name__}"
    )


urlpatterns = _unwrap(getattr(_tf_urls, 'urlpatterns', None))
app_name = 'two_factor'
