import pytest
from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction

from apps.identity.phone import InvalidPhone

User = get_user_model()


@pytest.mark.django_db
def test_an_email_user_is_stored_lower_case_with_a_hashed_password():
    user = User.objects.create_user(email="  Ama@Example.COM ", password="s3cret-pass-phrase")
    assert user.email == "ama@example.com" and user.phone is None
    assert user.password != "s3cret-pass-phrase" and user.check_password("s3cret-pass-phrase")
    assert not user.is_staff and not user.is_superuser


@pytest.mark.django_db
def test_a_phone_user_is_stored_in_one_format_and_cannot_log_in_with_a_password():
    user = User.objects.create_user(phone="024 123 4567")
    assert user.phone == "+233241234567" and user.email is None
    assert not user.has_usable_password()


@pytest.mark.django_db
def test_a_user_needs_an_email_or_a_phone_number():
    with pytest.raises(ValueError):
        User.objects.create_user()
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.bulk_create([User(full_name="nobody")])  # skips save(): the database refuses


@pytest.mark.django_db
def test_an_invalid_phone_number_is_refused():
    with pytest.raises(InvalidPhone):
        User.objects.create_user(phone="+14155552671")


@pytest.mark.django_db
def test_the_same_person_cannot_register_twice_however_they_type_it():
    User.objects.create_user(email="ama@example.com", phone="0241234567")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(email="AMA@example.com")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(phone="+233 24 123 4567")


@pytest.mark.django_db
def test_many_users_may_have_no_email_or_no_phone():
    User.objects.create_user(phone="0241111111")
    User.objects.create_user(phone="0242222222")
    User.objects.create_user(email="a@example.com")
    User.objects.create_user(email="b@example.com")
    assert User.objects.count() == 4


@pytest.mark.django_db
def test_saving_a_user_directly_still_normalises_the_phone_number():
    user = User(email="x@example.com", phone="0241234567")
    user.save()
    assert user.phone == "+233241234567"
    user.phone = ""
    user.save()
    assert user.phone is None


@pytest.mark.django_db
def test_superusers_are_staff_and_cannot_be_made_otherwise():
    admin = User.objects.create_superuser(email="boss@example.com", password="s3cret-pass-phrase")
    assert admin.is_staff and admin.is_superuser
    with pytest.raises(ValueError):
        User.objects.create_superuser(email="x@example.com", password="p", is_staff=False)


@pytest.mark.django_db
def test_login_ignores_case_and_stray_spaces_in_the_email():
    User.objects.create_user(email="ama@example.com", password="s3cret-pass-phrase")
    assert authenticate(username=" AMA@Example.com ", password="s3cret-pass-phrase") is not None
    assert authenticate(username="ama@example.com", password="wrong") is None


@pytest.mark.django_db
def test_inactive_users_cannot_log_in():
    user = User.objects.create_user(email="ama@example.com", password="s3cret-pass-phrase")
    user.is_active = False
    user.save()
    assert authenticate(username="ama@example.com", password="s3cret-pass-phrase") is None


@pytest.mark.django_db
def test_str_prefers_email_then_phone():
    both = User.objects.create_user(email="a@example.com", phone="0241234567")
    assert str(both) == "a@example.com"
    assert str(User.objects.create_user(phone="0242222222")) == "+233242222222"


# --- admin ---------------------------------------------------------------------------------


@pytest.mark.django_db
def test_user_admin_pages_load(admin_client, admin_user):
    for url in (
        "/admin/identity/user/",
        "/admin/identity/user/add/",
        f"/admin/identity/user/{admin_user.pk}/change/",
    ):
        assert admin_client.get(url).status_code == 200, url


@pytest.mark.django_db
def test_staff_can_create_a_user_in_the_admin_with_any_phone_spelling(admin_client):
    response = admin_client.post(
        "/admin/identity/user/add/",
        {
            "email": "Kofi@Example.com",
            "phone": "024 555 0101",
            "full_name": "Kofi",
            "password1": "correct-horse-battery-staple-91",
            "password2": "correct-horse-battery-staple-91",
        },
    )
    assert response.status_code == 302
    user = User.objects.get(email="kofi@example.com")
    assert user.phone == "+233245550101"


@pytest.mark.django_db
def test_a_bad_phone_number_in_the_admin_is_a_form_error_not_a_crash(admin_client):
    response = admin_client.post(
        "/admin/identity/user/add/",
        {
            "email": "kofi@example.com",
            "phone": "+14155552671",
            "full_name": "Kofi",
            "password1": "correct-horse-battery-staple-91",
            "password2": "correct-horse-battery-staple-91",
        },
    )
    assert response.status_code == 200
    assert not User.objects.filter(email="kofi@example.com").exists()
