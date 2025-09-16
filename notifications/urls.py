from .views import *
from django.urls import path


urlpatterns = [
    path("", inbox, name="inbox"),
    path("<int:pk>/read/", read, name="read"),
    path("read-all/", read_all, name="read_all"),
    # NEW for the navbar slider
    path("panel/", panel, name="panel"),
    path("<int:pk>/read-go/", read_go, name="read_go"),
]
