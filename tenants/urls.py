from django.urls import path
from . import views

urlpatterns = [
    path("payments/new/", views.new_payment, name="new_payment"),
    path("evaluators/new/", views.new_evaluator, name="new_evaluator"),
    path("suppliers/new/", views.new_supplier, name="new_supplier"),
    path("evaluator-users/new/", views.new_evaluator_user, name="new_evaluator_user"),
    path("evaulators/", views.evaluators_list, name="evaluator_detail"),
]
app_name = "tenants"

urlpatterns += [
    path("suppliers/<int:pk>/", views.supplier_detail, name="supplier_detail"),
    path("suppliers/<int:pk>/rules/upload/", views.rules_upload, name="rules_upload"),
]
