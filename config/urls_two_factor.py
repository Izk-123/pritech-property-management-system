"""
Wrapper URLconf for django-two-factor-auth.

Django's include() requires the included module to declare `app_name` at
module level when a namespace is used. The django-two-factor-auth package
(1.18.1) doesn't declare it, so this thin wrapper re-exports the URL
patterns with the required app_name set.

Include this module — not `two_factor.urls` — from both URLconfs:

    path('', include('config.urls_two_factor')),

Pure positional include() with a string module path. Django reads
`app_name` from the wrapper and uses it as the namespace, so URL names
become `two_factor:login`, `two_factor:setup`, etc.
"""

from two_factor.urls import urlpatterns  # noqa: F401

app_name = 'two_factor'