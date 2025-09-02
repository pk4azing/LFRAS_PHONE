from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings

from tenants.policies import PLAN_POLICIES
from .forms import ContactForm
from .models import ContactMessage


def home(request):
    return render(request, "marketing/home.html")


def about(request):
    return render(request, "marketing/about.html")


def products(request):
    # You can list key product pillars here; static for now
    return render(request, "marketing/products.html")


def pricing(request):
    order = ["ENTERPRISE", "PROFESSIONAL", "ESSENTIALS"]
    plans = [(code, PLAN_POLICIES[code]) for code in order]
    return render(request, "marketing/pricing.html", {"plans": plans})


def contact(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            cm = ContactMessage.objects.create(**form.cleaned_data)
            # Notify sales (console backend in dev)
            subject = f"[Lucid] Contact form — {cm.name} ({cm.email})"
            body = (
                f"Name: {cm.name}\nEmail: {cm.email}\nCompany: {cm.company}\n\n"
                f"Message:\n{cm.message}\n"
            )
            send_mail(
                subject,
                body,
                getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@lucidcompliances.com"),
                [getattr(settings, "SALES_EMAIL", "sales@lucidcompliances.com")],
                fail_silently=True,
            )
            messages.success(request, "Thanks! We’ve received your message.")
            return redirect("marketing:contact_thanks")
    else:
        form = ContactForm()
    return render(request, "marketing/contact.html", {"form": form})


def contact_thanks(request):
    return render(request, "marketing/contact_thanks.html")
