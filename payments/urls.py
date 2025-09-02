from django.urls import path
from . import views

app_name = "payments"

urlpatterns = [
    path("", views.list_payments, name="list"),
    path("records/new/", views.create_record, name="create_record"),
    path("transactions/new/", views.create_transaction, name="create_transaction"),
    path("records/<int:pk>/", views.record_detail, name="detail"),
]
