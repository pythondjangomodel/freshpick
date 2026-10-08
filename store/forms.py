from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Address, User


class SignupForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ["username", "email", "phone_number"]


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = [
            "full_name",
            "phone_number",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "pincode",
            "country",
        ]