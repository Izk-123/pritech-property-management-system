"""
DRF permission classes for the multi-tenant Pritech PMS.

These enforce that API access is scoped to the current tenant and
(optionally) to a specific role within that tenant.

Satisfies AZ-01 (RBAC), AZ-02 (property scoping), AZ-04 (CRUD per
role), and AZ-08 (explicit permission classes).
"""
from rest_framework.permissions import BasePermission

from apps.shared.users.models import UserTenantMembership


class HasTenantAccess(BasePermission):
    """
    User must be authenticated and have an active membership in the
    current tenant (or be a platform admin / superuser).
    """
    message = 'You do not have access to this tenant.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        tenant = getattr(request, 'tenant', None)
        if not tenant or tenant.schema_name == 'public':
            return False

        if request.user.is_platform_admin or request.user.is_superuser:
            return True

        return UserTenantMembership.objects.filter(
            user=request.user,
            tenant=tenant,
            is_active=True,
        ).exists()


class HasRolePermission(BasePermission):
    """
    User must have one of `required_roles` within the current tenant.

    Override `required_roles` in a subclass:

        class IsManagerOrAdmin(HasRolePermission):
            required_roles = ['TADMIN', 'MGR']
    """
    message = 'Your role does not permit this action.'
    required_roles = []

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Platform admins bypass role checks
        if request.user.is_platform_admin or request.user.is_superuser:
            return True

        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return False

        return UserTenantMembership.objects.filter(
            user=request.user,
            tenant=tenant,
            role__in=self.required_roles,
            is_active=True,
        ).exists()


# ── Pre-built role gates ────────────────────────────────────────────

class IsTenantAdmin(HasRolePermission):
    required_roles = ['TADMIN']


class IsManagerOrAdmin(HasRolePermission):
    required_roles = ['TADMIN', 'MGR']


class IsFrontDeskOrAbove(HasRolePermission):
    required_roles = ['TADMIN', 'MGR', 'FD']


class IsAccountantOrAbove(HasRolePermission):
    required_roles = ['TADMIN', 'ACC']


class IsPropertyAgentOrAbove(HasRolePermission):
    required_roles = ['TADMIN', 'MGR', 'AGT']


# ── Object-level property scoping ───────────────────────────────────

class PropertyScopedPermission(BasePermission):
    """
    Object-level check: the user must have access to the object's
    property.

    If the user has no property-level assignments, they see everything
    in the tenant. If they have assignments, the object's property
    must be in the set.
    """

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        user = request.user

        if user.is_platform_admin or user.is_superuser:
            return True

        # Try to find property assignments for this user
        try:
            from apps.core.properties.models import StaffPropertyAssignment
        except ImportError:
            return True  # No model → no scoping

        assigned = list(
            StaffPropertyAssignment.objects.filter(
                user=user, is_active=True,
            ).values_list('property_id', flat=True)
        )

        # No assignments → full tenant access
        if not assigned:
            return True

        # Find the object's property id
        obj_property_id = getattr(obj, 'property_id', None)
        if obj_property_id is None and hasattr(obj, 'property'):
            obj_property_id = getattr(obj.property, 'id', None)
        if obj_property_id is None and hasattr(obj, 'unit'):
            obj_property_id = getattr(obj.unit, 'property_id', None)

        return obj_property_id in assigned