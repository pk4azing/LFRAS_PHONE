from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from accounts.models import Roles
from accounts.models import User
from django.db import transaction
from .forms import TicketForm, TicketUpdateForm, CommentForm, AttachmentForm
from .models import Ticket, TicketStatus


def _status_widgets_qs(user):
    base = Ticket.objects.all()
    # later you can filter by user role if needed
    counts = base.values("status").annotate(c=Count("id"))
    map_counts = {c["status"]: c["c"] for c in counts}

    return [
        {"code": code, "label": label, "count": map_counts.get(code, 0)}
        for code, label in Ticket.STATUS_CHOICES
    ]

def _least_loaded_lus():
    lus = User.objects.filter(role=Roles.LUS, is_active=True).annotate(n=Count("tickets_assigned")).order_by("n", "id")
    return lus.first() or User.objects.filter(role=Roles.LAD, is_active=True).first()


def _auto_assign(user, supplier=None):
    """Assignment policy per your spec."""
    if user.role in [Roles.LAD, Roles.LUS]:
        return user
    if user.role in [Roles.EAD, Roles.EVS]:
        return _least_loaded_lus()
    if user.role == Roles.SUS:
        return _least_loaded_lus()
    return None


@login_required
def ticket_list(request):
    tickets = Ticket.objects.all().select_related("assignee", "created_by")
    ctx = {
        "tickets": tickets,
        "widgets": _status_widgets_qs(request.user),
    }
    return render(request, "tickets/list.html", ctx)


@login_required
def create_ticket(request):
    if request.method == "POST":
        form = TicketForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                t: Ticket = form.save(commit=False)

                # Always set created_by
                t.created_by = request.user

                # Normalize optional FKs by role
                role = request.user.role

                # If assignee wasn’t provided and your model requires it,
                # choose a default (e.g., self or the least-loaded LUS/LAD).
                if not t.assignee_id:
                    fallback = User.objects.filter(
                        role__in=[Roles.LUS, Roles.LAD], is_active=True
                    ).order_by('id').first()
                    t.assignee = fallback or request.user

                # If your business rules say evaluator/supplier may be missing,
                # make sure your model allows null=True on those fields.
                if role in [Roles.EVS, Roles.EAD]:
                    # supplier should not be user-pickable here
                    t.supplier = None
                if role in [Roles.SUS]:
                    # evaluator should be their evaluator; if you derive it elsewhere,
                    # ensure it’s set here or allow null=True in the model.
                    if not t.evaluator_id:
                        t.evaluator = None

                t.full_clean()  # fail fast with ValidationError instead of DB error
                t.save()
                messages.success(request, "Ticket created.")
                return redirect("tickets:detail", t.pk)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = TicketForm()
    return render(request, "tickets/create.html", {"form": form})


@login_required
def ticket_detail(request, pk: int):
    t = get_object_or_404(Ticket.objects.select_related("assignee", "created_by"), pk=pk)
    ctx = {
        "t": t,
        "update_form": TicketUpdateForm(instance=t),
        "comment_form": CommentForm(),
        "attach_form": AttachmentForm(),
        "widgets": _status_widgets_qs(request.user),
    }
    return render(request, "tickets/detail.html", ctx)


@login_required
def add_comment(request, pk: int):
    t = get_object_or_404(Ticket, pk=pk)
    if request.method == "POST":
        f = CommentForm(request.POST)
        if f.is_valid():
            c = f.save(commit=False)
            c.ticket = t
            c.author = request.user
            c.save()
            messages.success(request, "Comment added.")
    return redirect("tickets:detail", pk=pk)


@login_required
def add_attachment(request, pk: int):
    t = get_object_or_404(Ticket, pk=pk)
    if request.method == "POST":
        f = AttachmentForm(request.POST, request.FILES)
        if f.is_valid():
            a = f.save(commit=False)
            a.ticket = t
            a.uploaded_by = request.user
            a.save()
            messages.success(request, "Attachment uploaded.")
    return redirect("tickets:detail", pk=pk)


@login_required
def update_status(request, pk: int):
    t = get_object_or_404(Ticket, pk=pk)
    if request.method == "POST":
        f = TicketUpdateForm(request.POST, instance=t)
        if f.is_valid():
            f.save()
            messages.success(request, "Ticket updated.")
    return redirect("tickets:detail", pk=pk)