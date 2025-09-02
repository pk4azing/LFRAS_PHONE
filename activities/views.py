from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import Q, Count
from django.http import FileResponse, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.http import FileResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404

from accounts.models import Roles, User
from .forms import ActivityFileUploadForm, ActivityStartForm
from .models import Activity, ActivityFile, ActivityStatus, FileStatus
from .services import (
    visible_activities_qs,
    zip_activity,
)
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import Activity, ActivityFile, ActivityStatus, FileStatus
from accounts.models import Roles


def _can_manage_files(user, activity: Activity) -> bool:
    # SUS of that supplier can manage while IN_PROGRESS; EAD/EVS can view but not delete (per your rules)
    if user.role == Roles.SUS and user.supplier_id == activity.supplier_id:
        return activity.status == ActivityStatus.IN_PROGRESS
    return False


# If your audit + notifications helpers live elsewhere, adjust imports:
try:
    from auditlog.services import log_event
except Exception:

    def log_event(*args, **kwargs):  # no-op if audit not wired yet
        return None


try:
    from notifications.services import notify, Level
except Exception:

    class Level:
        INFO = "info"
        WARNING = "warning"
        ERROR = "error"

    def notify(*args, **kwargs):
        return None


# ---------- role guards ----------


def _can_view(user: User, a: Activity) -> bool:
    if user.role in (Roles.LAD, Roles.LUS):
        return True  # Lucid can view
    if user.role in (Roles.EAD, Roles.EVS):
        return getattr(user, "evaluator_id", None) == a.evaluator_id
    if user.role == Roles.SUS:
        return getattr(user, "supplier_id", None) == a.supplier_id
    return False


def _can_upload(user: User, a: Activity) -> bool:
    # Per your rule, only SUS can actually upload/start
    return (
        user.role == Roles.SUS and getattr(user, "supplier_id", None) == a.supplier_id
    )


def _can_start(user: User, evaluator_id: int, supplier_id: int) -> bool:
    return user.role == Roles.SUS and getattr(user, "supplier_id", None) == supplier_id


# ---------- list ----------


@login_required
def list_activities(request):
    qs = visible_activities_qs(request.user).select_related("evaluator", "supplier")
    qs = qs.order_by("-started_at", "-id")
    return render(request, "activities/list.html", {"activities": qs})


# ---------- start ----------


@login_required
@transaction.atomic
def start_activity(request):
    if request.method == "POST":
        form = ActivityStartForm(request.POST, user=request.user)
        if form.is_valid():
            evaluator = form.cleaned_data["evaluator"]
            supplier = form.cleaned_data["supplier"]
            if not _can_start(request.user, evaluator.id, supplier.id):
                messages.error(request, "Only the Supplier user can start an activity.")
                return redirect("activities:list")

            a = Activity.objects.create(
                evaluator=evaluator,
                supplier=supplier,
                status=ActivityStatus.IN_PROGRESS,
                started_by=request.user,
                started_at=timezone.now(),
            )
            log_event(
                request=request,
                actor=request.user,
                verb="started",
                action="activity.start",
                target=a,
                evaluator_id=evaluator.id,
                supplier_id=supplier.id,
            )
            notify(
                request.user,
                f"Activity started — {supplier.name}",
                body=f"Activity #{a.id} started by {request.user.email}",
                level=Level.INFO,
                link_url=f"/activities/{a.id}/",
                email=True,
            )
            messages.success(request, f"Activity #{a.id} started.")
            return redirect("activities:detail", pk=a.id)
    else:
        form = ActivityStartForm(user=request.user)

    return render(request, "activities/start.html", {"form": form})


# ---------- detail ----------


@login_required
def activity_detail(request, pk: int):
    a = get_object_or_404(visible_activities_qs(request.user), pk=pk)
    if not _can_view(request.user, a):
        return HttpResponseForbidden("Not allowed")

    files = a.files.select_related("uploaded_by").order_by("uploaded_at")

    # Supplier validation rule coverage (summary)
    coverage = _rule_coverage(a)

    # can end only if in progress, no failed files, and required coverage OK
    any_active_rules, required_missing = (
        coverage["any_active_rules"],
        coverage["required_missing"],
    )
    can_end = (
        a.status == ActivityStatus.IN_PROGRESS
        and not a.files.filter(status=FileStatus.VALID_FAILED).exists()
        and (not any_active_rules or not required_missing)
    )

    return render(
        request,
        "activities/detail.html",
        {"a": a, "files": files, "coverage": coverage, "can_end": can_end},
    )


# ---------- upload ----------


@login_required
@require_POST
@transaction.atomic
def upload_file(request, pk: int):
    a = get_object_or_404(visible_activities_qs(request.user), pk=pk)
    if not _can_upload(request.user, a):
        return HttpResponseForbidden(
            "Only Supplier users can upload files to this activity."
        )

    if a.status != ActivityStatus.IN_PROGRESS:
        messages.error(request, "Activity is not in progress.")
        return redirect("activities:detail", pk=a.id)

    form = ActivityFileUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Invalid file.")
        return redirect("activities:detail", pk=a.id)

    f = form.cleaned_data["file"]
    original_name = f.name

    # Versioning: next logical version for this file name
    last = (
        a.files.filter(original_name=original_name)
        .order_by("-version", "-uploaded_at")
        .first()
    )
    next_version = (last.version + 1) if last else 1

    af = ActivityFile.objects.create(
        activity=a,
        uploaded_by=request.user,
        original_name=original_name,
        file=f,  # storage backend handles path (your upload_to=activity_file_upload_path)
        status=FileStatus.UPLOADING,
        version=next_version,
        reupload_of=last if last else None,
    )
    # Move to validating
    af.status = FileStatus.VALIDATING
    af.save(update_fields=["status"])

    ok, reason = _validate_activity_file(af)
    af.status = FileStatus.VALID_OK if ok else FileStatus.VALID_FAILED
    af.failure_reason = "" if ok else (reason or "Validation failed")
    af.validated_at = timezone.now()
    af.save(update_fields=["status", "failure_reason", "validated_at"])

    log_event(
        request=request,
        actor=request.user,
        verb="uploaded",
        action="activity.file.upload",
        target=af,
        evaluator_id=a.evaluator_id,
        supplier_id=a.supplier_id,
        metadata={"original_name": original_name, "version": af.version, "ok": ok},
    )

    if ok:
        messages.success(request, f"Uploaded {original_name} (v{af.version}) ✓")
    else:
        messages.error(
            request, f"{original_name} failed validation: {af.failure_reason}"
        )

    return redirect("activities:detail", pk=a.id)


# ---------- reupload ----------


@login_required
@require_POST
@transaction.atomic
def reupload_file(request, file_id: int):
    prior = get_object_or_404(ActivityFile, pk=file_id)
    a = prior.activity
    if not _can_upload(request.user, a):
        return HttpResponseForbidden(
            "Only Supplier users can re-upload files to this activity."
        )
    if a.status != ActivityStatus.IN_PROGRESS:
        messages.error(request, "Activity is not in progress.")
        return redirect("activities:detail", pk=a.id)

    form = ActivityFileUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Invalid file.")
        return redirect("activities:detail", pk=a.id)

    f = form.cleaned_data["file"]
    original_name = prior.original_name
    next_version = prior.version + 1

    af = ActivityFile.objects.create(
        activity=a,
        uploaded_by=request.user,
        original_name=original_name,
        file=f,
        status=FileStatus.UPLOADING,
        version=next_version,
        reupload_of=prior,
    )
    af.status = FileStatus.VALIDATING
    af.save(update_fields=["status"])

    ok, reason = _validate_activity_file(af)
    af.status = FileStatus.VALID_OK if ok else FileStatus.VALID_FAILED
    af.failure_reason = "" if ok else (reason or "Validation failed")
    af.validated_at = timezone.now()
    af.save(update_fields=["status", "failure_reason", "validated_at"])

    log_event(
        request=request,
        actor=request.user,
        verb="reuploaded",
        action="activity.file.reupload",
        target=af,
        evaluator_id=a.evaluator_id,
        supplier_id=a.supplier_id,
        metadata={"original_name": original_name, "version": af.version, "ok": ok},
    )

    if ok:
        messages.success(request, f"Re-uploaded {original_name} (v{af.version}) ✓")
    else:
        messages.error(request, f"Re-upload failed: {af.failure_reason}")

    return redirect("activities:detail", pk=a.id)


# ---------- file status (AJAX poll) ----------


@login_required
def file_status(request, file_id: int):
    af = get_object_or_404(ActivityFile.objects.select_related("activity"), pk=file_id)
    if not _can_view(request.user, af.activity):
        return HttpResponseForbidden("Not allowed")
    data = {
        "id": af.id,
        "status": af.status,
        "failure_reason": af.failure_reason,
        "version": af.version,
        "uploaded_at": af.uploaded_at.isoformat() if af.uploaded_at else None,
        "validated_at": af.validated_at.isoformat() if af.validated_at else None,
    }
    return JsonResponse(data)


# ---------- end activity ----------


@login_required
@require_POST
@transaction.atomic
def end_activity(request, pk: int):
    """
    End an activity: POST only, must be IN_PROGRESS, must have zero failed files,
    and (if rules exist) no missing required files.
    """
    a = get_object_or_404(visible_activities_qs(request.user), pk=pk)
    if not _can_view(request.user, a):
        return HttpResponseForbidden("Not allowed")

    if a.status in (ActivityStatus.COMPLETED, ActivityStatus.CANCELLED):
        messages.info(request, "Activity already ended.")
        return redirect("activities:detail", pk=a.id)

    # failed files?
    if a.files.filter(status=FileStatus.VALID_FAILED).exists():
        messages.error(
            request, "Resolve failed files or re‑upload before ending the activity."
        )
        return redirect("activities:detail", pk=a.id)

    coverage = _rule_coverage(a)
    if coverage["any_active_rules"] and coverage["required_missing"]:
        messages.error(request, "Required files are missing based on validation rules.")
        return redirect("activities:detail", pk=a.id)

    # finalize
    a.status = ActivityStatus.COMPLETED
    a.ended_by = request.user
    a.ended_at = timezone.now()
    a.save(update_fields=["status", "ended_by", "ended_at"])

    archive = zip_activity(a)  # implement to place zip under .../Files/zipped/

    log_event(
        request=request,
        actor=request.user,
        verb="completed",
        action="activity.end",
        target=a,
        evaluator_id=a.evaluator_id,
        supplier_id=a.supplier_id,
        metadata={
            "zip": getattr(archive, "zip_file", None) and archive.zip_file.name,
            "total": a.files.count(),
            "failed": a.files.filter(status=FileStatus.VALID_FAILED).count(),
            "reuploads": a.files.exclude(reupload_of=None).count(),
        },
    )

    notify(
        request.user,
        f"Activity completed — {a.supplier.name}",
        body=f"Files: {a.files.count()}, Re-uploads: {a.files.exclude(reupload_of=None).count()}",
        level=Level.INFO,
        link_url=f"/activities/{a.id}/",
        email=True,
    )

    messages.success(request, "Activity ended and zipped.")
    return redirect("activities:detail", pk=a.id)


# ---------- download zip ----------


@login_required
def download_zip(request, pk: int):
    a = get_object_or_404(visible_activities_qs(request.user), pk=pk)
    if not _can_view(request.user, a):
        return HttpResponseForbidden("Not allowed")

    archive = zip_activity(a, create_if_missing=True)
    if not archive or not getattr(archive, "zip_file", None):
        messages.error(request, "ZIP not available.")
        return redirect("activities:detail", pk=a.id)

    response = FileResponse(
        archive.zip_file.open("rb"),
        as_attachment=True,
        filename=archive.zip_file.name.split("/")[-1],
    )
    return response


# ---------- helpers: validation & coverage ----------


def _validate_activity_file(af: ActivityFile) -> tuple[bool, str]:
    """
    Validate ActivityFile against SupplierValidationRule for the activity's supplier.
    Rules model fields (assumed):
      - supplier (FK)
      - expected_name (str, e.g., "w9" or "insurance_certificate.pdf")
      - required (bool)
      - required_keywords (pipe-separated, e.g., "policy|insurance|liability")
      - allowed_extensions (pipe-separated, e.g., "pdf|png|jpg")
      - active (bool)
    Logic:
      - If no active rules exist: accept.
      - Find a rule whose expected_name is contained in the original filename (case-insensitive).
      - Enforce extension and required_keywords if rule matched.
      - If no rule matched but there ARE required rules: fail; else accept.
    """
    try:
        from tenants.models import SupplierValidationRule as Rule
    except Exception:
        return True, ""  # rules not available → accept

    rules = Rule.objects.filter(supplier=af.activity.supplier, active=True)
    if not rules.exists():
        return True, ""

    name = (af.original_name or "").lower()

    # match by inclusion of expected_name
    matched = None
    for r in rules:
        exp = (r.expected_name or "").strip().lower()
        if exp and exp in name:
            matched = r
            break

    if not matched:
        if rules.filter(required=True).exists():
            return False, "No matching expected file for this upload."
        return True, ""

    # extension check
    if matched.allowed_extensions:
        exts = [
            e.strip().lower().lstrip(".")
            for e in matched.allowed_extensions.split("|")
            if e.strip()
        ]
        fname_ext = name.rsplit(".", 1)[-1] if "." in name else ""
        if exts and fname_ext not in exts:
            return (
                False,
                f"Extension '.{fname_ext}' not allowed. Expected: {', '.join(exts)}.",
            )

    # keywords check
    if matched.required_keywords:
        kws = [
            k.strip().lower() for k in matched.required_keywords.split("|") if k.strip()
        ]
        missing = [kw for kw in kws if kw not in name]
        if missing:
            return False, f"Missing required keywords: {', '.join(missing)}."

    return True, ""


def _rule_coverage(a: Activity) -> dict:
    """
    Return summary about rule coverage and missing required docs.
    """
    try:
        from tenants.models import SupplierValidationRule as Rule
    except Exception:
        return {"any_active_rules": False, "required_missing": [], "matched_counts": {}}

    rules = list(Rule.objects.filter(supplier=a.supplier, active=True))
    if not rules:
        return {"any_active_rules": False, "required_missing": [], "matched_counts": {}}

    files = a.files.all()
    matched_counts = {}
    for r in rules:
        exp = (r.expected_name or "").strip().lower()
        if not exp:
            continue
        count = sum(
            1
            for f in files
            if exp in (f.original_name or "").lower()
            and f.status == FileStatus.VALID_OK
        )
        matched_counts[exp] = count

    required_missing = []
    for r in rules:
        if r.required:
            exp = (r.expected_name or "").strip().lower()
            if not exp:
                continue
            if matched_counts.get(exp, 0) == 0:
                required_missing.append(r.expected_name)

    return {
        "any_active_rules": True,
        "required_missing": required_missing,
        "matched_counts": matched_counts,
    }


@login_required
def download_file(request, file_id: int):
    af = get_object_or_404(ActivityFile.objects.select_related("activity"), pk=file_id)
    a = af.activity
    # reuse your visibility check; if you don't have _can_view, use your existing guard
    if not _can_view(request.user, a):
        return HttpResponseForbidden("Not allowed")
    filename = af.original_name or af.file.name.split("/")[-1]
    return FileResponse(af.file.open("rb"), as_attachment=True, filename=filename)


@login_required
def activity_status_json(request, pk: int):
    a = get_object_or_404(visible_activities_qs(request.user), pk=pk)
    data = []
    for f in a.files.all().order_by("uploaded_at"):
        data.append(
            {
                "id": f.id,
                "status": f.status,
                "failure_reason": f.failure_reason or "",
            }
        )
    return JsonResponse({"ok": True, "files": data})


@login_required
@require_POST
def delete_file(request, pk: int, file_id: int):
    a = get_object_or_404(visible_activities_qs(request.user), pk=pk)
    f = get_object_or_404(a.files, pk=file_id)
    if not _can_manage_files(request.user, a):
        return HttpResponseForbidden("Not allowed")
    # allow delete only if not VALID_OK (optional rule; change as needed)
    if f.status == FileStatus.VALID_OK:
        messages.error(
            request, "Cannot delete a validated file. Re-upload to replace instead."
        )
        return redirect("activities:detail", pk=a.id)
    f.delete()
    messages.success(request, "File removed.")
    return redirect("activities:detail", pk=a.id)
