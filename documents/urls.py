from django.urls import path
from . import views

urlpatterns = [
    path("", views.list_documents, name="list"),
    path("<int:pk>/", views.document_detail, name="detail"),
    path("upload/", views.upload_document, name="upload"),
    path("<int:pk>/download/", views.download_document, name="download"),
    path("zip/", views.download_zip, name="download_zip"),
    # NEW: reminders preview
    path("reminders/preview/", views.reminders_preview, name="reminders_preview"),
]
