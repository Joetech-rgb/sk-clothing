from apps.messaging.providers import FakeEmailProvider, FakeSmsProvider, SendResult


def test_a_retried_sms_with_the_same_key_is_sent_once():
    sms = FakeSmsProvider()
    first = sms.send("+233241234567", "Your code is on the order page", idempotency_key="order-1")
    again = sms.send("+233241234567", "Your code is on the order page", idempotency_key="order-1")
    assert first == again and len(sms.sent) == 1
    sms.send("+233241234567", "Another message", idempotency_key="order-2")
    assert len(sms.sent) == 2


def test_a_retried_email_with_the_same_key_is_sent_once():
    mail = FakeEmailProvider()
    for _ in range(3):
        result = mail.send("a@example.com", "Order", "Thanks", idempotency_key="order-1-email")
    assert result.accepted and len(mail.sent) == 1


def test_send_results_say_whether_to_retry():
    assert SendResult(accepted=False, error="timeout", retryable=True).retryable
    assert not SendResult(accepted=True).retryable
