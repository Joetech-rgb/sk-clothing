import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from apps.messaging import services
from apps.messaging.factory import fake_sms
from apps.messaging.models import OutboxMessage
from apps.messaging.providers import SendResult

PHONE = "+233201234567"  # a made-up number
SECRET_TEXT = "your code is 123456"


class Stub:
    def __init__(self, result, delay=0.0):
        self.result = result
        self.delay = delay
        self.calls = 0

    def send(self, to_e164, text, *, idempotency_key):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        return self.result


class Raises:
    def send(self, to_e164, text, *, idempotency_key):
        raise RuntimeError(f"boom {to_e164} {text}")


@pytest.fixture(autouse=True)
def fake_provider(settings):
    settings.SMS_PROVIDER = "fake"
    fake_sms().sent.clear()
    fake_sms()._seen.clear()


def queue(key="k1", **kwargs):
    return services.queue_sms(
        to_e164=PHONE,
        text=SECRET_TEXT,
        template="test",
        idempotency_key=key,
        enqueue=False,
        **kwargs,
    )


def use(monkeypatch, provider):
    monkeypatch.setattr(services, "get_sms_provider", lambda: provider)


@pytest.mark.django_db
def test_queuing_the_same_key_twice_makes_one_message():
    first, created_first = queue("same")
    second, created_second = queue("same")
    assert (created_first, created_second) == (True, False)
    assert first.pk == second.pk and OutboxMessage.objects.count() == 1


@pytest.mark.django_db
def test_a_key_is_required():
    with pytest.raises(ValueError):
        queue("")


@pytest.mark.django_db
def test_a_due_message_is_sent_once_and_its_body_is_cleared():
    message, _ = queue()
    assert services.deliver(message.pk) == "sent"
    assert services.deliver(message.pk) == services.SKIPPED  # a second run does nothing
    assert fake_sms().sent == [(PHONE, SECRET_TEXT)]
    message.refresh_from_db()
    assert message.status == "sent" and message.body == "" and message.sent_at is not None
    assert message.attempts == 1 and message.provider_id.startswith("fake-sms-")


@pytest.mark.django_db
def test_a_retryable_failure_is_kept_and_retried_later(monkeypatch):
    use(monkeypatch, Stub(SendResult(accepted=False, error="timeout", retryable=True)))
    message, _ = queue()
    assert services.deliver(message.pk) == "pending"
    message.refresh_from_db()
    assert message.attempts == 1 and message.last_error == "timeout"
    assert message.body == SECRET_TEXT  # still needed for the retry
    assert message.next_attempt_at > timezone.now()
    assert services.deliver(message.pk) == services.SKIPPED  # not due yet


@pytest.mark.django_db
def test_a_message_that_is_not_retryable_fails_and_is_not_tried_again(monkeypatch):
    stub = Stub(SendResult(accepted=False, error="invalid_number", retryable=False))
    use(monkeypatch, stub)
    message, _ = queue()
    assert services.deliver(message.pk) == "failed"
    message.refresh_from_db()
    assert message.body == "" and message.last_error == "invalid_number"
    assert services.deliver(message.pk) == services.SKIPPED and stub.calls == 1


@pytest.mark.django_db
def test_a_message_gives_up_after_the_maximum_attempts(monkeypatch):
    use(monkeypatch, Stub(SendResult(accepted=False, error="timeout", retryable=True)))
    message, _ = queue()
    status = ""
    for _ in range(services.MAX_ATTEMPTS):
        OutboxMessage.objects.filter(pk=message.pk).update(next_attempt_at=timezone.now())
        status = services.deliver(message.pk)
    assert status == "failed"
    message.refresh_from_db()
    assert message.attempts == services.MAX_ATTEMPTS and message.body == ""


@pytest.mark.django_db
def test_a_provider_that_raises_is_retried_and_leaks_nothing_to_the_log(monkeypatch, caplog):
    use(monkeypatch, Raises())
    message, _ = queue()
    with caplog.at_level(logging.DEBUG):
        assert services.deliver(message.pk) == "pending"
    assert PHONE not in caplog.text
    assert SECRET_TEXT not in caplog.text
    assert "123456" not in caplog.text
    message.refresh_from_db()
    assert message.last_error == "provider_exception"


@pytest.mark.django_db
def test_backoff_grows_and_is_capped():
    waits = [services.backoff(n).total_seconds() for n in range(1, 9)]
    assert waits[:4] == [60, 120, 240, 480]
    assert max(waits) == 3600 and waits == sorted(waits)


@pytest.mark.django_db
def test_due_ids_lists_only_waiting_messages_that_are_due():
    due, _ = queue("due")
    later, _ = queue("later")
    sent, _ = queue("sent")
    OutboxMessage.objects.filter(pk=later.pk).update(
        next_attempt_at=timezone.now() + timedelta(hours=1)
    )
    OutboxMessage.objects.filter(pk=sent.pk).update(status="sent")
    assert services.due_ids() == [due.pk]


@pytest.mark.django_db
def test_stuck_messages_are_released_but_recent_ones_are_not():
    old, _ = queue("old")
    recent, _ = queue("recent")
    now = timezone.now()
    OutboxMessage.objects.filter(pk=old.pk).update(
        status="sending", claimed_at=now - services.STUCK_AFTER - timedelta(minutes=1)
    )
    OutboxMessage.objects.filter(pk=recent.pk).update(status="sending", claimed_at=now)
    assert services.release_stuck() == 1
    old.refresh_from_db()
    recent.refresh_from_db()
    assert (old.status, recent.status) == ("pending", "sending")


@pytest.mark.django_db
def test_str_does_not_show_the_recipient_or_body():
    message, _ = queue()
    assert PHONE not in str(message) and SECRET_TEXT not in str(message)


@pytest.mark.django_db(transaction=True)
def test_two_workers_racing_for_one_message_send_it_once(monkeypatch):
    stub = Stub(SendResult(accepted=True, provider_id="x"), delay=0.3)
    use(monkeypatch, stub)
    message, _ = queue()

    def worker():
        try:
            return services.deliver(message.pk)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    assert sorted(results) == ["sent", services.SKIPPED]
    assert stub.calls == 1
