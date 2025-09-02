from __future__ import annotations
import io, zipfile
from types import SimpleNamespace
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone

from accounts.models import Roles, User
from .models import Activity


def visible_activities_qs(user: User):
    qs = Activity.objects.all()
    if user.role in (Roles.LAD, Roles.LUS):
        return qs
    if user.role in (Roles.EAD, Roles.EVS):
        return qs.filter(evaluator_id=getattr(user, "evaluator_id", None))
    if user.role == Roles.SUS:
        return qs.filter(supplier_id=getattr(user, "supplier_id", None))
    return qs.none()


def _zip_key_for_activity(a: Activity, ts=None):
    ts = ts or timezone.now()
    fname = f"activity_{a.id}_{ts.strftime('%Y%m%d_%H%M%S')}.zip"
    return f"Evaluator/{a.evaluator_id}/Supplier/{a.supplier_id}/Activity/{a.id}/Files/zipped/{fname}"


def zip_activity(a: Activity, create_if_missing: bool = True):
    """
    Create a ZIP of all successful files and write it to default storage (S3).
    Returns an object with `.zip_file` that mimics a FileField (has name, open()).
    """
    # Build zip in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for af in a.files.all():
            try:
                # Only include actual stored file; use original name + version
                path = af.file.name
                arcname = f"{af.original_name}"
                if af.version and af.version > 1:
                    # append version before extension
                    if "." in arcname:
                        base, ext = arcname.rsplit(".", 1)
                        arcname = f"{base}_v{af.version}.{ext}"
                    else:
                        arcname = f"{arcname}_v{af.version}"
                with default_storage.open(path, "rb") as fh:
                    zf.writestr(arcname, fh.read())
            except Exception:
                # skip any missing file but continue
                continue

    if not create_if_missing and buf.getbuffer().nbytes == 0:
        return None

    key = _zip_key_for_activity(a)
    content = ContentFile(buf.getvalue())
    saved_name = default_storage.save(key, content)

    # Return a light wrapper with .zip_file.name and .zip_file.open()
    class _ZipWrapper:
        name = saved_name

        def open(self, mode="rb"):
            return default_storage.open(saved_name, mode)

    return SimpleNamespace(zip_file=_ZipWrapper())
