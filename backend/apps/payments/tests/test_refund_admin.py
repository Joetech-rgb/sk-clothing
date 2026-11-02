import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

from apps.orders.models import OrderEvent
from apps.payments import refunds
from apps.payments.client import PaystackError
from apps.payments.models import PaymentAttempt, Refund
from apps.payments.tests.helpers import fake, order_row, refund_requested_order

pytestmark = pytest.mark.django_db

REFUNDS = "/admin/payments/refund/"
PAYMENTS = "/admin/payments/paymentattempt/"
PASSWORD = "pw-12345-xyz"


def staff(email, *codenames, is_staff=True):
    user = get_user_model().objects.create_user(email=email, password=PASSWORD, is_staff=is_staff)
    if codenames:
        user.user_permissions.set(Permission.objects.filter(codename__in=codenames))
    return user


def login(client, user):
    client.force_login(user)
    return client


@pytest.fixture(autouse=True)
def an_earlier_user(db):
    """So the staff members in these tests do not all have id 1, and a wrong id shows up."""
    staff("earlier@example.com")


def manual_refund(shop):
    order, reference = refund_requested_order(shop)
    fake().fail_refund_create = PaystackError("no", retryable=False)
    refunds.process_refunds(fake())
    fake().fail_refund_create = None
    refund = Refund.objects.get(payment__reference=reference)
    assert refund.status == "manual_resolution"
    return order, refund


def test_staff_can_record_a_refund_made_outside_the_system(shop, client):
    order, refund = manual_refund(shop)
    user = staff("ama@example.com", "view_refund", "change_refund")
    response = login(client, user).post(
        f"{REFUNDS}{refund.pk}/change/",
        {
            "outcome": "resolved_outside",
            "note": "Refunded in the Paystack dashboard",
            "events-TOTAL_FORMS": "0",
            "events-INITIAL_FORMS": "0",
        },
    )
    assert response.status_code == 302
    refund.refresh_from_db()
    assert refund.status == "processed" and refund.resolved_by == f"user:{user.pk}"
    assert refund.resolution_note == "Refunded in the Paystack dashboard"
    assert order_row(order["reference"]).refund == "processed"
    assert refund.events.last().actor == f"user:{user.pk}"
    assert (
        OrderEvent.objects.filter(
            order__reference=order["reference"], event="refund_resolved_manually"
        ).count()
        == 1
    )


@pytest.mark.parametrize(
    "data", [{"outcome": "resolved_outside", "note": ""}, {"outcome": "bogus", "note": "x"}]
)
def test_a_missing_note_or_unknown_outcome_changes_nothing(shop, client, data):
    _, refund = manual_refund(shop)
    user = staff("ama@example.com", "view_refund", "change_refund")
    response = login(client, user).post(
        f"{REFUNDS}{refund.pk}/change/",
        {**data, "events-TOTAL_FORMS": "0", "events-INITIAL_FORMS": "0"},
    )
    assert response.status_code == 200
    refund.refresh_from_db()
    assert refund.status == "manual_resolution" and refund.resolved_by == ""


def test_a_refund_that_does_not_need_a_person_cannot_be_resolved_here(shop, client):
    order, reference = refund_requested_order(shop)
    refunds.process_refunds(fake())
    refund = Refund.objects.get()
    assert refund.status == "submitted"
    user = staff("ama@example.com", "view_refund", "change_refund")
    response = login(client, user).post(
        f"{REFUNDS}{refund.pk}/change/",
        {
            "outcome": "resolved_outside",
            "note": "done",
            "events-TOTAL_FORMS": "0",
            "events-INITIAL_FORMS": "0",
        },
    )
    assert response.status_code == 200
    refund.refresh_from_db()
    assert refund.status == "submitted"


def test_staff_cannot_edit_the_amount_or_status_directly(shop, client):
    _, refund = manual_refund(shop)
    user = staff("ama@example.com", "view_refund", "change_refund")
    login(client, user).post(
        f"{REFUNDS}{refund.pk}/change/",
        {
            "amount_pesewas": 1,
            "status": "processed",
            "outcome": "",
            "note": "",
            "events-TOTAL_FORMS": "0",
            "events-INITIAL_FORMS": "0",
        },
    )
    refund.refresh_from_db()
    assert refund.status == "manual_resolution" and refund.amount_pesewas > 1


def test_without_the_change_permission_nothing_can_be_resolved(shop, client):
    _, refund = manual_refund(shop)
    viewer = staff("viewer@example.com", "view_refund")
    c = login(client, viewer)
    assert c.get(REFUNDS).status_code == 200
    response = c.post(f"{REFUNDS}{refund.pk}/change/", {"outcome": "resolved_outside", "note": "x"})
    assert response.status_code == 403
    refund.refresh_from_db()
    assert refund.status == "manual_resolution"


def test_staff_with_no_permissions_and_customers_are_kept_out(shop, client):
    _, refund = manual_refund(shop)
    assert login(client, staff("nobody@example.com")).get(REFUNDS).status_code == 403
    customer = staff("shopper@example.com", "change_refund", is_staff=False)
    response = login(client, customer).get(REFUNDS)
    assert response.status_code == 302 and "login" in response["Location"]


def test_refunds_cannot_be_added_or_deleted_from_the_admin(shop, client):
    _, refund = manual_refund(shop)
    everything = ("view_refund", "add_refund", "change_refund", "delete_refund")
    c = login(client, staff("powerful@example.com", *everything))
    assert c.get(f"{REFUNDS}add/").status_code == 403
    assert c.post(f"{REFUNDS}{refund.pk}/delete/", {"post": "yes"}).status_code == 403
    assert Refund.objects.count() == 1


def test_the_payments_list_is_read_only_and_shows_the_ones_that_need_a_person(shop, client):
    refund_requested_order(shop)
    everything = (
        "view_paymentattempt",
        "add_paymentattempt",
        "change_paymentattempt",
        "delete_paymentattempt",
    )
    c = login(client, staff("auditor@example.com", *everything))
    assert c.get(PAYMENTS).status_code == 200
    assert c.get(f"{PAYMENTS}?status=duplicate").status_code == 200
    attempt = PaymentAttempt.objects.get()
    assert c.get(f"{PAYMENTS}add/").status_code == 403
    assert c.post(f"{PAYMENTS}{attempt.pk}/change/", {"status": "failed"}).status_code == 403
    assert c.post(f"{PAYMENTS}{attempt.pk}/delete/", {"post": "yes"}).status_code == 403
    attempt.refresh_from_db()
    assert attempt.status == "success"
