from django.urls import path
from . import views

app_name = "auditlog"

urlpatterns = [
    path("export/", views.export_form, name="export_form"),
    path("export.csv", views.export_csv, name="export_csv"),
]
