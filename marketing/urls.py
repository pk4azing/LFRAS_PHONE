from django.urls import path
from .views import home, about, products, pricing, contact, contact_thanks

urlpatterns = [
    path("", home, name="marketing_home"),
    path("about/", about, name="about"),
    path("products/", products, name="products"),
    path("pricing/", pricing, name="pricing"),
    path("contact/", contact, name="contact"),
    path("contact/thanks/", contact_thanks, name="contact_thanks"),
]
