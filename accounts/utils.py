import secrets, string
from django.contrib.auth import get_user_model

User = get_user_model()

ALPHABET = string.ascii_letters + string.digits


def generate_temp_password(length=10):
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def invite_user(email, role, **extra):
    """
    Create or reset a user for first-login flow: sets must_change_password=True
    Returns (user, temp_password, created:bool)
    """
    temp = generate_temp_password()
    extra.pop("role", None)  # Remove role from extra to avoid conflicts
    u, created = User.objects.get_or_create(
        email=email, defaults={"role": role, **extra}
    )
    u.role = role
    u.set_password(temp)
    u.must_change_password = True
    for k, v in extra.items():
        setattr(u, k, v)
    u.is_active = True
    u.save()
    return u, temp, created
