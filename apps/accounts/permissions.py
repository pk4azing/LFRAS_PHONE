from rest_framework import permissions

class IsLD(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "LD"

class IsLDSuperAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and u.role == "LD" and u.is_superuser

class IsCDAdminOrLD(permissions.BasePermission):
    """
    - LD can do anything here
    - CD_ADMIN can manage users in their own tenant
    - Others: read-only (if you want to allow), blocked by default
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.role == "LD":
            return True
        if request.user.role == "CD_ADMIN":
            return True
        # read-only fallback (optional)
        return request.method in permissions.SAFE_METHODS

    def has_object_permission(self, request, view, obj):
        u = request.user
        if u.role == "LD":
            return True
        if u.role == "CD_ADMIN":
            return getattr(obj, "cd_id", None) == u.cd_id
        return request.method in permissions.SAFE_METHODS