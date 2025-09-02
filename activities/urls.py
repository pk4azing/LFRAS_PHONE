from django.urls import path
from . import views

app_name = "activities"

urlpatterns = [
    path("", views.list_activities, name="list"),
    path("start/", views.start_activity, name="start"),
    path("<int:pk>/", views.activity_detail, name="detail"),
    path("<int:pk>/upload/", views.upload_file, name="upload"),
    path("reupload/<int:file_id>/", views.reupload_file, name="reupload"),
    path("<int:pk>/end/", views.end_activity, name="end"),
    path("<int:pk>/zip/", views.download_zip, name="zip"),
    path("file/<int:file_id>/status/", views.file_status, name="file_status"),
    path("file/<int:file_id>/download/", views.download_file, name="download_file"),
    path("<int:pk>/status.json", views.activity_status_json, name="status_json"),
    path("<int:pk>/file/<int:file_id>/delete/", views.delete_file, name="delete_file"),
]
