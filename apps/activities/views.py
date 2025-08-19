from datetime import datetime, timedelta, date
from django.db.models import Q
from django.utils.timezone import now
from django.db.models.functions import TruncDate
from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import Activity, ActivityFile
from .calendar import CalendarEventSerializer
from .serializers import (
    ActivitySerializer, ActivityWriteSerializer,
    ActivityFileSerializer, ActivityFileWriteSerializer
)
from apps.accounts.utils import add_notification, add_audit
from apps.tenants.utils import email_with_tenant

class ActivityViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['period','status','s3_prefix']

    def get_queryset(self):
        qs = Activity.objects.select_related('cd','ccd').prefetch_related('files').all()
        u = self.request.user
        if u.role != 'LD':
            qs = qs.filter(cd_id=u.cd_id or -1)
        # filters
        if (period := self.request.query_params.get('period')):
            qs = qs.filter(period=period)
        if (ccd := self.request.query_params.get('ccd')):
            qs = qs.filter(ccd_id=ccd)
        if (status_q := self.request.query_params.get('status')):
            qs = qs.filter(status=status_q)
        if (q := self.request.query_params.get('q')):
            qs = qs.filter(Q(s3_prefix__icontains=q) | Q(period__icontains=q))
        return qs.order_by('-created_at')

    def get_serializer_class(self):
        if self.action in ('create','update','partial_update'):
            return ActivityWriteSerializer
        return ActivitySerializer

    def perform_create(self, serializer):
        obj = serializer.save()
        cd = obj.cd
        # In-app: CCD (if any) + POCs
        if obj.ccd:
            add_notification(obj.ccd, cd, f"Activity {obj.id} created (period={obj.period}).",
                             "ACTIVITY_CREATED", actor=self.request.user)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        for poc in User.objects.filter(cd=cd, role="CD_ADMIN"):
            add_notification(poc, cd, f"Activity {obj.id} created for period {obj.period}.",
                             "ACTIVITY_CREATED", actor=self.request.user)
        # Audit
        add_audit(actor=self.request.user, cd=cd, event="ACTIVITY_CREATED",
                  meta={'activity_id': obj.id, 'period': obj.period, 'status': obj.status})

    def perform_update(self, serializer):
        old = self.get_object()
        prev_status = old.status
        obj = serializer.save()
        cd = obj.cd

        # Detect status change
        if prev_status != obj.status:
            msg = f"Activity {obj.id} status: {prev_status} → {obj.status}."
            if obj.ccd:
                add_notification(obj.ccd, cd, msg, "ACTIVITY_STATUS_CHANGED", actor=self.request.user)
            from django.contrib.auth import get_user_model
            User = get_user_model()
            for poc in User.objects.filter(cd=cd, role="CD_ADMIN"):
                add_notification(poc, cd, msg, "ACTIVITY_STATUS_CHANGED", actor=self.request.user)
            add_audit(actor=self.request.user, cd=cd, event="ACTIVITY_STATUS_CHANGED",
                      meta={'activity_id': obj.id, 'from': prev_status, 'to': obj.status})

            # Email for major transitions
            if obj.status.lower() in {"completed", "ready", "done"}:
                subject = f"LFRAS: Activity {obj.id} completed"
                text = f"Activity {obj.id} is completed for period {obj.period}."
                html = f"<p>Activity <b>{obj.id}</b> is <b>completed</b> for period <b>{obj.period}</b>.</p>"
                if obj.ccd and obj.ccd.email:
                    email_with_tenant(cd, obj.ccd.email, subject, text, html)
                for poc_email in User.objects.filter(cd=cd, role="CD_ADMIN").values_list('email', flat=True):
                    if poc_email:
                        email_with_tenant(cd, poc_email, subject, text, html)

    @action(detail=True, methods=['post'], url_path='notify-reminder')
    def remind(self, request, pk=None):
        """Manual reminder trigger for CCD & POCs (optional convenience)."""
        obj = self.get_object()
        cd = obj.cd
        from django.contrib.auth import get_user_model
        User = get_user_model()
        if obj.ccd:
            add_notification(obj.ccd, cd, f"Reminder for Activity {obj.id} (period={obj.period}).",
                             "ACTIVITY_REMINDER", actor=request.user)
        for poc in User.objects.filter(cd=cd, role="CD_ADMIN"):
            add_notification(poc, cd, f"Reminder triggered for Activity {obj.id}.",
                             "ACTIVITY_REMINDER", actor=request.user)
        add_audit(actor=request.user, cd=cd, event="ACTIVITY_REMINDER",
                  meta={'activity_id': obj.id})
        return Response({'detail': 'Reminder queued.'}, status=status.HTTP_200_OK)

class ActivityFileViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = ActivityFile.objects.select_related('activity','activity__cd').all()
        u = self.request.user
        if u.role != 'LD':
            qs = qs.filter(activity__cd_id=u.cd_id or -1)
        if (aid := self.request.query_params.get('activity')):
            qs = qs.filter(activity_id=aid)
        if (status_q := self.request.query_params.get('validation_status')):
            qs = qs.filter(validation_status=status_q)
        return qs.order_by('-uploaded_at')

    def get_serializer_class(self):
        if self.action in ('create','update','partial_update'):
            return ActivityFileWriteSerializer
        return ActivityFileSerializer

    def perform_create(self, serializer):
        obj = serializer.save()
        act = obj.activity
        cd = act.cd
        # Notify CCD + POCs
        if act.ccd:
            add_notification(act.ccd, cd, f"File '{obj.original_name}' uploaded for Activity {act.id}.",
                             "ACTIVITYFILE_UPLOADED", actor=self.request.user)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        for poc in User.objects.filter(cd=cd, role="CD_ADMIN"):
            add_notification(poc, cd, f"File '{obj.original_name}' uploaded for Activity {act.id}.",
                             "ACTIVITYFILE_UPLOADED", actor=self.request.user)
        # Audit
        add_audit(actor=self.request.user, cd=cd, event="ACTIVITYFILE_UPLOADED",
                  meta={'activity_id': act.id, 'file_id': obj.id, 'name': obj.original_name})

    @action(detail=True, methods=['post'], url_path='downloaded')
    def mark_downloaded(self, request, pk=None):
        """Call this when a file is downloaded externally (signed URL flow)."""
        obj = self.get_object()
        act = obj.activity
        cd = act.cd
        from django.contrib.auth import get_user_model
        User = get_user_model()
        for poc in User.objects.filter(cd=cd, role="CD_ADMIN"):
            add_notification(poc, cd, f"Activity file downloaded: {obj.original_name} (Activity {act.id}).",
                             "ACTIVITYFILE_DOWNLOADED", actor=request.user)
        add_audit(actor=request.user, cd=cd, event="ACTIVITYFILE_DOWNLOADED",
                  meta={'activity_id': act.id, 'file_id': obj.id, 'name': obj.original_name})
        return Response({'detail': 'Download recorded.'}, status=status.HTTP_200_OK)
    


class CalendarFeedView(APIView):
    """
    GET /api/v1/activities/calendar/?start=YYYY-MM-DD&end=YYYY-MM-DD[&cd=<id>]
    Returns a flat list of calendar events your FE can render with colors.

    Colors (suggested):
      INFO -> #28a745 (green)
      WARNING -> #ffc107 (yellow)
      EXPIRY -> #dc3545 (red)
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # --- Parse range ---
        try:
            start_str = request.query_params.get("start")
            end_str = request.query_params.get("end")
            if start_str and end_str:
                start = datetime.strptime(start_str, "%Y-%m-%d").date()
                end = datetime.strptime(end_str, "%Y-%m-%d").date()
            else:
                # default to current month range
                today = now().date()
                start = today.replace(day=1)
                # first day next month - 1
                if start.month == 12:
                    end = date(start.year + 1, 1, 1) - timedelta(days=1)
                else:
                    end = date(start.year, start.month + 1, 1) - timedelta(days=1)
        except ValueError:
            return Response({"detail": "Invalid start/end date format. Use YYYY-MM-DD."},
                            status=status.HTTP_400_BAD_REQUEST)

        if end < start:
            return Response({"detail": "end must be >= start"}, status=status.HTTP_400_BAD_REQUEST)

        # --- Scope by role/tenant ---
        u = request.user
        qs_activity = Activity.objects.select_related("cd", "ccd")
        qs_file = ActivityFile.objects.select_related("activity", "activity__cd")

        if u.role != "LD":
            # auto-scope to user's tenant
            qs_activity = qs_activity.filter(cd_id=u.cd_id or -1)
            qs_file = qs_file.filter(activity__cd_id=u.cd_id or -1)
        else:
            # LD can filter by cd if provided
            cd_filter = request.query_params.get("cd")
            if cd_filter:
                qs_activity = qs_activity.filter(cd_id=cd_filter)
                qs_file = qs_file.filter(activity__cd_id=cd_filter)

        # --- Build events ---
        events = []

        # 1) INFO (new activity) — use created_at date
        acts = (
            qs_activity
            .filter(created_at__date__gte=start, created_at__date__lte=end)
            .annotate(day=TruncDate("created_at"))
            .values("id", "day", "cd_id", "period", "status")
        )
        for a in acts:
            events.append({
                "date": a["day"],
                "kind": "INFO",
                "title": f"Activity #{a['id']} created",
                "description": f"Period {a['period']} (status: {a['status']})",
                "cd": a["cd_id"],
                "activity_id": a["id"],
                "file_id": None,
                "color": "#28a745",
            })

        # 2) WARNING/EXPIRY from ActivityFile.expiry_at
        #    - EXPIRY (red) when expiry_at == today
        #    - WARNING (yellow) when today < expiry_at <= today + 30 days
        today = now().date()
        warn_until = today + timedelta(days=30)

        files = (
            qs_file
            .filter(expiry_at__isnull=False, expiry_at__date__gte=start, expiry_at__date__lte=end)
            .annotate(day=TruncDate("expiry_at"))
            .values("id", "day", "activity_id", "activity__cd_id", "original_name")
        )

        for f in files:
            expiry_day = f["day"]
            if expiry_day == today:
                kind = "EXPIRY"
                color = "#dc3545"
                title = f"Expiry: {f['original_name']}"
            elif today < expiry_day <= warn_until:
                kind = "WARNING"
                color = "#ffc107"
                title = f"Upcoming expiry: {f['original_name']}"
            else:
                # not within warning horizon → skip (keeps payload light)
                continue

            events.append({
                "date": expiry_day,
                "kind": kind,
                "title": title,
                "description": f"Activity #{f['activity_id']} file",
                "cd": f["activity__cd_id"],
                "activity_id": f["activity_id"],
                "file_id": f["id"],
                "color": color,
            })

        # You can optionally sort by date (and maybe by kind priority)
        events.sort(key=lambda e: (e["date"], {"EXPIRY":0,"WARNING":1,"INFO":2}.get(e["kind"], 3)))

        return Response(CalendarEventSerializer(events, many=True).data, status=status.HTTP_200_OK)