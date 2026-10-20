from django import forms
from django.contrib.auth.forms import BaseUserCreationForm, UserChangeForm

from .models import User
from .phone import InvalidPhone, normalise_ghana_phone


def clean_phone_value(raw: str | None) -> str | None:
    """Staff may type a number in any common spelling; store it in one form, or say why not."""
    if not raw:
        return None
    try:
        return normalise_ghana_phone(raw)
    except InvalidPhone as error:
        raise forms.ValidationError(str(error)) from error


class StaffUserCreationForm(BaseUserCreationForm):
    class Meta:
        model = User
        fields = ("email", "phone", "full_name")

    def clean_phone(self) -> str | None:
        return clean_phone_value(self.cleaned_data.get("phone"))


class StaffUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User

    def clean_phone(self) -> str | None:
        return clean_phone_value(self.cleaned_data.get("phone"))
