from accounts.models import Roles


def can_manage_payments(user):
    return user.is_authenticated and user.role == Roles.LAD


def can_view_payments(user):
    return user.is_authenticated and user.role in (Roles.LAD, Roles.LUS)
