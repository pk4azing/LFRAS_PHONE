from django.utils import timezone
from django.db.models import Q
from django.contrib.auth import get_user_model
from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Ticket, TicketComment
from .serializers import TicketSerializer, TicketWriteSerializer, TicketCommentSerializer
from apps.accounts.utils import add_notification, add_audit
from apps.tenants.utils import email_with_tenant

User = get_user_model()


class TicketViewSet(viewsets.ModelViewSet):
    """
    /api/v1/tickets/
      - list/create/retrieve/update/partial_update
    Role scoping:
      - LD: can see all tenants; filter ?cd=
      - CD/CCD: only their own cd
    """
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['title', 'description']

    def get_queryset(self):
        qs = Ticket.objects.select_related('cd', 'created_by', 'assigned_to').all()
        u = self.request.user
        if u.role != 'LD':
            qs = qs.filter(cd_id=u.cd_id or -1)

        # Filters
        cd = self.request.query_params.get('cd')
        status_q = self.request.query_params.get('status')
        assigned = self.request.query_params.get('assigned_to')
        created_by = self.request.query_params.get('created_by')
        q = self.request.query_params.get('q')

        if cd:
            qs = qs.filter(cd_id=cd)
        if status_q:
            qs = qs.filter(status=status_q)
        if assigned:
            qs = qs.filter(assigned_to_id=assigned)
        if created_by:
            qs = qs.filter(created_by_id=created_by)
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
        return qs.order_by('-created_at')

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return TicketWriteSerializer
        return TicketSerializer

    def perform_create(self, serializer):
        obj = serializer.save()  # created_by set in serializer
        cd = obj.cd
        actor = self.request.user

        # Notify creator
        add_notification(actor, cd, f"Ticket #{obj.id} created.", "TICKET_CREATED", actor=actor)
        # Notify assigned LD (if any)
        if obj.assigned_to and obj.assigned_to.email:
            add_notification(obj.assigned_to, cd, f"Ticket #{obj.id} assigned to you.", "TICKET_ASSIGNED", actor=actor)
            email_with_tenant(cd, obj.assigned_to.email,
                              subject=f"LFRAS: Ticket #{obj.id} assigned",
                              body_text=f"Ticket #{obj.id} [{obj.title}] has been assigned to you.",
                              body_html=f"<p>Ticket <b>#{obj.id}</b> [{obj.title}] has been assigned to you.</p>")
        # Notify CD POCs
        for poc in User.objects.filter(cd=cd, role="CD_ADMIN"):
            add_notification(poc, cd, f"Ticket #{obj.id} created.", "TICKET_CREATED", actor=actor)

        # Audit
        add_audit(actor=actor, cd=cd, event="TICKET_CREATED", meta={'ticket_id': obj.id, 'priority': obj.priority})

    def perform_update(self, serializer):
        old = self.get_object()
        prev_status = old.status
        prev_assignee_id = old.assigned_to_id

        obj = serializer.save()
        cd = obj.cd
        actor = self.request.user

        # Detect changes
        changed = []
        if prev_status != obj.status:
            changed.append(f"status {prev_status}→{obj.status}")
        if prev_assignee_id != obj.assigned_to_id:
            changed.append("assignee changed")

        # Notifications
        if changed:
            msg = f"Ticket #{obj.id} updated ({'; '.join(changed)})."
        else:
            msg = f"Ticket #{obj.id} updated."

        # To creator (if exists)
        if obj.created_by:
            add_notification(obj.created_by, cd, msg, "TICKET_UPDATED", actor=actor)
        # To current assignee
        if obj.assigned_to:
            add_notification(obj.assigned_to, cd, msg, "TICKET_UPDATED", actor=actor)
        # To POCs
        for poc in User.objects.filter(cd=cd, role="CD_ADMIN"):
            add_notification(poc, cd, msg, "TICKET_UPDATED", actor=actor)

        # Email on status transitions (not every minor edit)
        if prev_status != obj.status:
            subject = f"LFRAS: Ticket #{obj.id} status {prev_status} → {obj.status}"
            text = f"Ticket #{obj.id} [{obj.title}] status changed: {prev_status} → {obj.status}."
            html = f"<p>Ticket <b>#{obj.id}</b> [{obj.title}] status changed: <b>{prev_status}</b> → <b>{obj.status}</b>.</p>"
            recipients = set()
            if obj.created_by and obj.created_by.email:
                recipients.add(obj.created_by.email)
            if obj.assigned_to and obj.assigned_to.email:
                recipients.add(obj.assigned_to.email)
            for poc in User.objects.filter(cd=cd, role="CD_ADMIN").values_list('email', flat=True):
                if poc:
                    recipients.add(poc)
            for email in recipients:
                email_with_tenant(cd, email, subject, text, html)

        # Auto-close timestamp
        if obj.status == "CLOSED" and not obj.closed_at:
            obj.closed_at = timezone.now()
            obj.save(update_fields=['closed_at'])

        # Audit
        add_audit(actor=actor, cd=cd, event="TICKET_UPDATED",
                  meta={'ticket_id': obj.id, 'changes': changed})

    @action(detail=True, methods=['post'], url_path='close')
    def close_ticket(self, request, pk=None):
        ticket = self.get_object()
        if ticket.status != "CLOSED":
            prev = ticket.status
            ticket.status = "CLOSED"
            ticket.closed_at = timezone.now()
            ticket.save(update_fields=['status', 'closed_at'])

            cd = ticket.cd
            actor = request.user
            msg = f"Ticket #{ticket.id} closed."

            # Notifications
            if ticket.created_by:
                add_notification(ticket.created_by, cd, msg, "TICKET_CLOSED", actor=actor)
            if ticket.assigned_to:
                add_notification(ticket.assigned_to, cd, msg, "TICKET_CLOSED", actor=actor)
            for poc in User.objects.filter(cd=cd, role="CD_ADMIN"):
                add_notification(poc, cd, msg, "TICKET_CLOSED", actor=actor)

            # Email
            subject = f"LFRAS: Ticket #{ticket.id} closed"
            text = f"Ticket #{ticket.id} [{ticket.title}] has been closed."
            html = f"<p>Ticket <b>#{ticket.id}</b> [{ticket.title}] has been <b>closed</b>.</p>"
            recipients = set()
            if ticket.created_by and ticket.created_by.email: recipients.add(ticket.created_by.email)
            if ticket.assigned_to and ticket.assigned_to.email: recipients.add(ticket.assigned_to.email)
            for e in User.objects.filter(cd=cd, role="CD_ADMIN").values_list('email', flat=True):
                if e: recipients.add(e)
            for email in recipients:
                email_with_tenant(cd, email, subject, text, html)

            # Audit
            add_audit(actor=actor, cd=cd, event="TICKET_CLOSED",
                      meta={'ticket_id': ticket.id, 'from': prev, 'to': 'CLOSED'})

        return Response(TicketSerializer(ticket).data, status=status.HTTP_200_OK)


class TicketCommentViewSet(viewsets.ModelViewSet):
    """
    /api/v1/tickets/<ticket_id>/comments/  (when nested via router) OR flat with ?ticket=
    """
    permission_classes = [permissions.IsAuthenticated]
    queryset = TicketComment.objects.select_related('ticket', 'author', 'ticket__cd').all()
    serializer_class = TicketCommentSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        if u.role != 'LD':
            qs = qs.filter(ticket__cd_id=u.cd_id or -1)
        if (tid := self.request.query_params.get('ticket')):
            qs = qs.filter(ticket_id=tid)
        return qs

    def perform_create(self, serializer):
        comment = serializer.save()
        t = comment.ticket
        cd = t.cd
        actor = self.request.user

        msg = f"New comment on Ticket #{t.id}."
        # notify creator + assignee + POCs
        if t.created_by:
            add_notification(t.created_by, cd, msg, "TICKET_COMMENTED", actor=actor)
        if t.assigned_to:
            add_notification(t.assigned_to, cd, msg, "TICKET_COMMENTED", actor=actor)
        for poc in User.objects.filter(cd=cd, role="CD_ADMIN"):
            add_notification(poc, cd, f"{msg}", "TICKET_COMMENTED", actor=actor)

        # Audit
        add_audit(actor=actor, cd=cd, event="TICKET_COMMENTED",
                  meta={'ticket_id': t.id, 'comment_id': comment.id})