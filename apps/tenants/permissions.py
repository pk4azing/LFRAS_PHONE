from rest_framework.permissions import BasePermission

class CanCreateCD(BasePermission):
    message = "Only LD users can create CD tenants."
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "LD"

class CanCreateCCD(BasePermission):
    message = "Only LD or CD Admins can create CCD tenants."
    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        if view.action != "create":
            return True
        if u.role == "LD":
            return True
        if u.role in ("CD_ADMIN",):
            return bool(u.cd_id)
        return False