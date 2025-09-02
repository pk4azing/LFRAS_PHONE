from django.urls import path
from . import views

urlpatterns = [
    path("supplier/<int:supplier_id>/", views.rules_list, name="rules_list"),
    path("supplier/<int:supplier_id>/new/", views.rule_create, name="rule_create"),
    path("rule/<int:pk>/edit/", views.rule_edit, name="rule_edit"),
    path("rule/<int:pk>/delete/", views.rule_delete, name="rule_delete"),
]
