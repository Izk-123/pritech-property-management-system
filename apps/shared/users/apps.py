from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.shared.users'
    label = 'shared_users'
    verbose_name = _('Team & Accounts')

    def ready(self):
        # Register the Chichewa language with Django
        from django.conf.locale import LANG_INFO
        LANG_INFO.setdefault('ny', {
            'bidi': False,
            'code': 'ny',
            'name': 'Chichewa',
            'name_local': 'Chichewa',
        })

        # Register auth event signal handlers (AZ-10)
        from . import signals  # noqa: F401

        self._harden_third_party_admins()

    @staticmethod
    def _harden_third_party_admins():
        """
        Wrap third-party admins that manage public-schema models with
        PublicSchemaOnlyAdminMixin.

        NOTE: this only works if django.contrib.admin appears BEFORE
        apps.shared.users in INSTALLED_APPS, because admin autodiscover
        (which registers the third-party admins) runs in admin's ready().
        If a model isn't registered yet, _wrap silently skips it — verify
        with the shell check in the notes.
        """
        from django.contrib import admin
        from apps.shared.tenants.admin_mixins import PublicSchemaOnlyAdminMixin

        def _wrap(model):
            if not admin.site.is_registered(model):
                return
            current = admin.site._registry[model]
            cls = current.__class__
            if issubclass(cls, PublicSchemaOnlyAdminMixin):
                return
            current.__class__ = type(
                'Scoped' + cls.__name__,
                (PublicSchemaOnlyAdminMixin, cls),
                {'__module__': cls.__module__},
            )

        try:
            from auditlog.models import LogEntry
            _wrap(LogEntry)
        except Exception:
            pass

        try:
            from django_celery_beat import models as beat_models
            # NB: the class is ClockedSchedule (capital S).
            for name in ('PeriodicTask', 'IntervalSchedule',
                         'CrontabSchedule', 'SolarSchedule',
                         'ClockedSchedule'):
                model = getattr(beat_models, name, None)
                if model:
                    _wrap(model)
        except Exception:
            pass

        try:
            from django_celery_results import models as results_models
            for name in ('TaskResult', 'GroupResult', 'ChordCounter'):
                model = getattr(results_models, name, None)
                if model:
                    _wrap(model)
        except Exception:
            pass

        try:
            from axes.models import AccessAttempt, AccessFailureLog, AccessLog
            for model in (AccessAttempt, AccessFailureLog, AccessLog):
                _wrap(model)
        except Exception:
            pass