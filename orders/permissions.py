from rest_framework.permissions import BasePermission


class IsStaffOrOwner(BasePermission):
    """Un client n'accède qu'à ses commandes ; un administrateur à toutes."""

    def has_object_permission(self, request, view, obj):
        return bool(request.user.is_staff or obj.customer_id == str(request.user.id))
