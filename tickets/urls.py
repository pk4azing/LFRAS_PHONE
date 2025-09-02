from django.urls import path
from . import views

app_name = "tickets"

urlpatterns = [
    path("", views.ticket_list, name="list"),
    path("new/", views.create_ticket, name="new"),
    path("<int:pk>/", views.ticket_detail, name="detail"),
    path("<int:pk>/comment/", views.add_comment, name="comment"),
    path("<int:pk>/attach/", views.add_attachment, name="attach"),
    path("<int:pk>/status/", views.update_status, name="status"),
]