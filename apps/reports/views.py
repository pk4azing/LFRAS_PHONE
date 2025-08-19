from rest_framework import viewsets, permissions, status, filters
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Q
from django.contrib.auth import get_user_model

from .models import Report
from .serializers import ReportSerializer, ReportRequestSerializer, ReportUpdateSerializer
from apps.accounts.utils import add_notification, add_audit
from apps.tenants.utils import email_with_tenant

User = get_user_model()


class ReportViewSet(viewsets.ModelViewSet):
    """
    /api/v1/reports/
      GET: list (role scoped)
      POST: request a report
    /api/v1/reports/<id>/
      GET: details
      PATCH: update status/keys (usually LD)
    /api/v1/reports/<id>/download/   (POST)
      mark a download event (notify + audit)
    """
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ["report_type", "s3_key", "failed_reason"]
    queryset = Report.objects.select_related("cd", "requested_by").all()

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        if u.role != "LD":
            qs = qs.filter(cd_id=u.cd_id or -1)
        # Optional filters
        if (status_q := self.request.query_params.get("status")):
            qs = qs.filter(status=status_q)
        if (rtype := self.request.query_params.get("report_type")):
            qs = qs.filter(report_type=rtype)
        if (cd := self.request.query_params.get("cd")) and u.role == "LD":
            qs = qs.filter(cd_id=cd)
        if (q := self.request.query_params.get("q")):
            qs = qs.filter(Q(failed_reason__icontains=q) | Q(s3_key__icontains=q))
        return qs.order_by("-requested_at")

    def get_serializer_class(self):
        if self.action == "create":
            return ReportRequestSerializer
        if self.action in ("update", "partial_update"):
            return ReportUpdateSerializer
        return ReportSerializer

    def perform_create(self, serializer):
        obj = serializer.save()  # requested_by set in serializer
        cd = obj.cd
        actor = self.request.user

        # notify requester + CD POCs
        add_notification(actor, cd, f"Report requested: {obj.report_type}.", "REPORT_REQUESTED", actor=actor)
        for poc in User.objects.filter(cd=cd, role="CD_ADMIN"):
            add_notification(poc, cd, f"Report requested: {obj.report_type}.", "REPORT_REQUESTED", actor=actor)

        # audit
        add_audit(actor=actor, cd=cd, event="REPORT_REQUESTED",
                  target_user=actor, meta={"report_id": obj.id, "type": obj.report_type})

    def perform_update(self, serializer):
        old = self.get_object()
        prev_status = old.status
        obj = serializer.save()
        cd = obj.cd

        if prev_status != obj.status:
            # notify requester + POCs
            msg = f"Report {obj.id} status: {prev_status} → {obj.status}."
            if obj.requested_by:
                add_notification(obj.requested_by, cd, msg, "REPORT_STATUS_CHANGED", actor=self.request.user)
            for poc in User.objects.filter(cd=cd, role="CD_ADMIN"):
                add_notification(poc, cd, msg, "REPORT_STATUS_CHANGED", actor=self.request.user)

            # audit
            add_audit(actor=self.request.user, cd=cd, event="REPORT_STATUS_CHANGED",
                      target_user=obj.requested_by,
                      meta={"report_id": obj.id, "from": prev_status, "to": obj.status})

            # email on READY
            if obj.status == "READY":
                subject = f"LFRAS: Report {obj.id} is ready"
                text = f"Your {obj.report_type} report is ready."
                html = f"<p>Your <b>{obj.report_type}</b> report is ready.</p>"
                if obj.requested_by and obj.requested_by.email:
                    email_with_tenant(cd, obj.requested_by.email, subject, text, html)
                for poc in User.objects.filter(cd=cd, role="CD_ADMIN").values_list("email", flat=True):
                    if poc:
                        email_with_tenant(cd, poc, subject, text, html)

    @action(detail=True, methods=["post"], url_path="download")
    def mark_download(self, request, pk=None):
        report = self.get_object()
        u = request.user

        # notify requester + POCs
        add_notification(u, report.cd, f"Report {report.id} downloaded.", "REPORT_DOWNLOADED", actor=u)
        for poc in User.objects.filter(cd=report.cd, role="CD_ADMIN"):
            add_notification(poc, report.cd, f"Report {report.id} downloaded by {u.email}.",
                             "REPORT_DOWNLOADED", actor=u)

        # audit
        add_audit(actor=u, cd=report.cd, event="REPORT_DOWNLOADED", target_user=u,
                  meta={"report_id": report.id, "type": report.report_type})

        # Your actual download flow would return a signed URL here
        return Response({"detail": "Download recorded."}, status=status.HTTP_200_OK)