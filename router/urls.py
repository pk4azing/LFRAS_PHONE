# router/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/", views.index, name="dashboard"),
    path("role-redirect/", views.index, name="role_redirect"),
    path("lad/", views.lad_dashboard, name="lad"),
    path("ead/", views.ead_dashboard, name="ead"),
    path("sus/", views.sus_dashboard, name="sus"),
    path("evs/", views.evs_dashboard, name="evs"),  # NEW
    path("lus/", views.lus_dashboard, name="lus"),  # NEW
]
