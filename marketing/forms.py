from django import forms


class ContactForm(forms.Form):
    name = forms.CharField(max_length=150, label="Your Name")
    email = forms.EmailField(label="Email")
    company = forms.CharField(max_length=150, required=False, label="Company")
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}), label="Message")
