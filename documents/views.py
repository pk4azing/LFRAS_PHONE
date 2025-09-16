from datetime import datetime, timedelta
from django.db.models import Q
import io
import os
import zipfile

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import Roles
from tenants.models import Supplier
from .forms import DocumentUploadForm
from .models import Document

# Audit + notifications
from auditlog.services import log_event
from notifications.models import Level
from notifications.services import notify

# Reminders preview helper
from .utils import will_trigger_on


# ---------- helpers ----------


def _scope_qs(user):
    """
    Documents visible to current user by role.
    LAD/LUS: all
    EAD/EVS: evaluator-scoped
    SUS: evaluator + their supplier
    """
    if not user.is_authenticated:
        return Document.objects.none()

    if user.role in (Roles.LAD, Roles.LUS):
        return Document.objects.all()

    if user.role in (Roles.EAD, Roles.EVS):
        return Document.objects.filter(evaluator=user.evaluator)

    if user.role == Roles.SUS:
        return Document.objects.filter(evaluator=user.evaluator, supplier=user.supplier)

    return Document.objects.none()


def _doc_scope(qs, user):
    if user.role in (Roles.EAD, Roles.EVS):
        return qs.filter(evaluator_id=user.evaluator_id)
    if user.role == Roles.SUS:
        return qs.filter(supplier_id=user.supplier_id)
    return qs


# ---------- views ----------


@login_required
def list_documents(request):
    qs = Document.objects.select_related("evaluator", "supplier").order_by(
        "expires_at", "title"
    )
    qs = _doc_scope(qs, request.user)

    expiring = (request.GET.get("expiring") or "").lower()
    today = timezone.localdate()
    if expiring == "week":
        qs = qs.filter(expires_at__date__range=[today, today + timedelta(days=7)])
    elif expiring == "month":
        qs = qs.filter(expires_at__date__range=[today, today + timedelta(days=30)])

    q = request.GET.get("q") or ""
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))

    return render(
        request, "documents/list.html", {"docs": qs, "q": q, "expiring": expiring}
    )


@login_required
def upload_document(request):
    """
    Upload rules:
      - EAD/EVS: evaluator-scoped; may choose supplier under their evaluator
      - SUS: fixed to their supplier
      - LAD/LUS: allowed, but must attach to a supplier to infer evaluator (Phase‑1)
    """
    if request.user.role not in (Roles.EAD, Roles.EVS, Roles.SUS, Roles.LAD, Roles.LUS):
        return HttpResponseForbidden("Not allowed")

    initial = {}
    if request.user.role in (Roles.EAD, Roles.EVS):
        initial["supplier"] = None
    if request.user.role == Roles.SUS:
        initial["supplier"] = request.user.supplier

    form = DocumentUploadForm(
        request.POST or None, request.FILES or None, initial=initial
    )

    # Limit supplier choices to the user's evaluator (for EAD/EVS/SUS)
    if request.user.role in (Roles.EAD, Roles.EVS, Roles.SUS):
        form.fields["supplier"].queryset = Supplier.objects.filter(
            evaluator_id=request.user.evaluator_id
        )

    if request.method == "POST" and form.is_valid():
        doc = form.save(commit=False)

        # Scope enforcement
        if request.user.role in (Roles.EAD, Roles.EVS):
            doc.evaluator = request.user.evaluator
            # supplier may be chosen from same evaluator (already constrained)
        elif request.user.role == Roles.SUS:
            doc.evaluator = request.user.evaluator
            doc.supplier = request.user.supplier
        else:
            # LAD/LUS must provide supplier so we can infer evaluator in Phase‑1
            if not doc.supplier:
                messages.error(
                    request, "Please attach the document to a specific supplier."
                )
                return render(request, "documents/upload.html", {"form": form})
            doc.evaluator = doc.supplier.evaluator

        doc.uploaded_by = request.user
        doc.save()

        # Audit
        log_event(
            request=request,
            actor=request.user,
            verb="uploaded",
            action="document.upload",
            target=doc,
            evaluator_id=doc.evaluator_id,
            supplier_id=doc.supplier_id,
            metadata={"title": doc.title, "category": doc.category},
        )

        # Notifications
        if request.user.role == Roles.SUS:
            # Supplier uploaded -> notify all EADs of evaluator
            for ead in request.user.evaluator.users.filter(
                role=Roles.EAD, is_active=True
            ):
                notify(
                    ead,
                    f"New supplier document: {doc.title}",
                    body=f"{request.user.supplier.name} uploaded a document.",
                    level=Level.INFO,
                    link_url="/documents/",
                    email=True,
                )
        elif request.user.role in (Roles.EAD, Roles.EVS) and doc.supplier_id:
            # Evaluator uploaded for a supplier -> notify SUS users
            for sus in doc.supplier.users.filter(role=Roles.SUS, is_active=True):
                notify(
                    sus,
                    f"New document from Evaluator: {doc.title}",
                    body=f"{doc.evaluator.name} uploaded a document.",
                    level=Level.INFO,
                    link_url="/documents/",
                    email=True,
                )

        messages.success(request, "Document uploaded.")
        return redirect("documents:list")

    return render(request, "documents/upload.html", {"form": form})


@login_required
def download_document(request, pk: int):
    """
    Single download. If storage backend gives a public/presigned URL (S3),
    redirect there; otherwise stream locally.
    """
    doc = get_object_or_404(_scope_qs(request.user), pk=pk)
    try:
        url = doc.file.url
    except Exception:
        url = None

    if url and url.startswith("http"):
        return redirect(url)

    f = doc.file.open("rb")
    filename = os.path.basename(doc.file.name)
    return FileResponse(f, as_attachment=True, filename=filename)


@login_required
def download_zip(request):
    """
    POST with 'ids' (one or many) to download a ZIP of chosen docs.
    """
    if request.method != "POST":
        return HttpResponseForbidden("POST only")

    # Accept both ids and ids[] styles
    ids = request.POST.getlist("ids") or request.POST.getlist("ids[]")
    docs = list(_scope_qs(request.user).filter(pk__in=ids))
    if not docs:
        messages.warning(request, "No documents selected.")
        return redirect("documents:list")

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in docs:
            try:
                with d.file.open("rb") as fh:
                    arcname = os.path.basename(d.file.name)
                    # avoid duplicate names in archive
                    if zf.namelist().count(arcname):
                        base, ext = os.path.splitext(arcname)
                        i = 2
                        newname = f"{base} ({i}){ext}"
                        while newname in zf.namelist():
                            i += 1
                            newname = f"{base} ({i}){ext}"
                        arcname = newname
                    zf.writestr(arcname, fh.read())
            except Exception:
                # skip unreadable/missing files
                continue

    mem.seek(0)
    resp = HttpResponse(mem.read(), content_type="application/zip")
    resp["Content-Disposition"] = 'attachment; filename="documents.zip"'
    return resp


# ---------- reminders preview (staff/LAD) ----------


@staff_member_required
def reminders_preview(request):
    """
    Staff preview: which docs would trigger reminders on a chosen date (default: today).
    Uses fixed schedule: 30/14/7/1 pre-expiry, on-day, weekly post-expiry.
    """
    qd = request.GET.get("date")
    if qd:
        try:
            run_date = datetime.strptime(qd, "%Y-%m-%d").date()
        except ValueError:
            run_date = timezone.localdate()
    else:
        run_date = timezone.localdate()

    qs = Document.objects.filter(
        is_active=True, expires_at__isnull=False
    ).select_related("evaluator", "supplier", "uploaded_by")

    rows = []
    summary = {"pre": 0, "on": 0, "post": 0}

    for d in qs:
        trig = will_trigger_on(d, run_date)
        if not trig:
            continue
        summary[trig.kind] += 1
        rows.append(
            {
                "doc": d,
                "kind": trig.kind,
                "days": trig.days,
                "expires": d.expires_at,
            }
        )

    # sort by type then days
    kind_order = {"pre": 0, "on": 1, "post": 2}
    rows.sort(key=lambda r: (kind_order[r["kind"]], r["days"]))

    return render(
        request,
        "documents/reminders_preview.html",
        {
            "run_date": run_date,
            "rows": rows,
            "summary": summary,
        },
    )


@login_required
def document_detail(request, pk):
    doc = get_object_or_404(
        _doc_scope(
            Document.objects.select_related("evaluator", "supplier"), request.user
        ),
        pk=pk,
    )
    return render(request, "documents/detail.html", {"doc": doc})
