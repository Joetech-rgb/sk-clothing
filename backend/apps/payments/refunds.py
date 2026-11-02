"""Refunds (ADR 0008): money goes back to the customer, exactly once, and nothing is lost track of.

How it works:
1. `queue_refunds` finds orders whose refund was requested (a paid order that could not be
   fulfilled, or was cancelled) and payments that arrived twice, and creates one Refund row per
   payment. The unique link to the payment means a double trigger can never refund twice.
2. `submit_refund` claims the row under a lock (only one runner can), records the attempt, and only
   then calls Paystack, with no database transaction open. The full amount is always stated, so a
   repeated request can never refund more than was paid.
3. `sync_refund` asks Paystack how an open refund is getting on. Paystack's own answer decides;
   refund webhooks are not used.
4. A refund Paystack cannot deliver is retried after a pause, a fixed number of times, and then
   goes to a person (`manual_resolution`). So do refunds that need the customer's bank details
   (Paystack's `needs-attention`), refunds Paystack refuses outright, and refunds whose outcome we
   cannot know (a request that was sent and never answered, followed by a refusal).
5. Staff can record that a refund was made outside the system. A refund unresolved after 24 hours
   raises an error in the logs (Sentry).

For a refund of an order, the order's own refund status follows the same steps (the state machine
in orders/states.py). A refund for a duplicate payment has no order status to move.

Never log an email address, a phone number or Paystack's own error text.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.orders import settlement
from apps.orders.services import transition
from apps.orders.states import Event, InvalidTransition

from .client import PaystackClient, PaystackError, RefundAnswer
from .models import PaymentAttempt, Refund, RefundEvent

logger = logging.getLogger(__name__)

DEFAULTS: dict[str, object] = {
    "max_attempts": 3,
    "backoff_minutes": (5, 30),  # the pause after the 1st and 2nd failed attempt
    "stuck_after_minutes": 10,  # sent, never answered
    "poll_every_minutes": 5,
    "overdue_after_hours": 24,
}

SKIPPED = "skipped"


def option(name: str):
    return getattr(settings, "REFUND_LIMITS", {}).get(name, DEFAULTS[name])


@dataclass(frozen=True)
class RunSummary:
    queued: int
    submitted: int
    synced: int
    stuck: int


def _log(refund: Refund, kind: str, actor: str = "system", detail: str = "") -> None:
    RefundEvent.objects.create(refund=refund, kind=kind, actor=actor, detail=detail[:300])


def _order_event(refund: Refund, event: Event) -> None:
    """Move the order's refund status along. Only refunds of an order have one."""
    if refund.reason != Refund.Reason.ORDER:
        return
    try:
        transition(refund.order_id, event, actor="system:refund")
    except InvalidTransition:
        logger.warning("refund %s: the order's refund status did not accept %s", refund.pk, event)


# --- 1. finding what needs refunding ------------------------------------------------------------


def _ensure_refund(attempt: PaymentAttempt, reason: str, now: datetime) -> bool:
    try:
        with transaction.atomic():
            refund = Refund.objects.create(
                payment=attempt,
                order_id=attempt.order_id,
                reason=reason,
                amount_pesewas=attempt.amount_pesewas,
                currency=attempt.currency,
                idempotency_key=f"refund:{attempt.reference}",
                next_attempt_at=now,
            )
            _log(refund, "requested", detail=reason)
    except IntegrityError:
        return False  # one already exists for this payment
    return True


def queue_refunds(*, now: datetime | None = None, limit: int = 200) -> int:
    """Create a Refund for every payment that needs one. Returns how many were created."""
    now = now or timezone.now()
    created = 0
    for order_id in settlement.orders_awaiting_refund(limit):
        paid = PaymentAttempt.objects.filter(
            order_id=order_id, status=PaymentAttempt.Status.SUCCESS
        ).first()
        if paid is None:
            logger.error("order %s needs a refund but has no confirmed payment", order_id)
            continue
        created += _ensure_refund(paid, Refund.Reason.ORDER, now)
    for paid in PaymentAttempt.objects.filter(
        status=PaymentAttempt.Status.DUPLICATE, refund__isnull=True
    )[:limit]:
        created += _ensure_refund(paid, Refund.Reason.DUPLICATE, now)
    return created


# --- 2. sending ---------------------------------------------------------------------------------


def _fail(refund_id: int, code: str, *, give_up: bool, now: datetime) -> str:
    """An attempt did not work. Retry after a pause, or hand over to a person."""
    with transaction.atomic():
        refund = Refund.objects.select_for_update().get(pk=refund_id)
        if refund.status not in (Refund.Status.SUBMITTED, Refund.Status.PROCESSING):
            return SKIPPED
        refund.last_error = code
        _order_event(refund, Event.REFUND_FAILED)
        if give_up or refund.attempts >= int(option("max_attempts")):
            refund.status = Refund.Status.MANUAL_RESOLUTION
            refund.next_attempt_at = None
            _order_event(refund, Event.REFUND_ESCALATED)
            _log(refund, "needs_a_person", detail=code)
            logger.error("refund %s needs a person (%s)", refund.pk, code)
        else:
            pauses = tuple(option("backoff_minutes"))
            pause = pauses[min(refund.attempts - 1, len(pauses) - 1)]
            refund.status = Refund.Status.REQUESTED
            refund.next_attempt_at = now + timedelta(minutes=pause)
            _order_event(refund, Event.REFUND_RETRY)
            _log(refund, "will_retry", detail=code)
        refund.save()
        return refund.status


def _apply_answer(refund_id: int, answer: RefundAnswer, now: datetime) -> str:
    """Record what Paystack says about a refund we have sent."""
    with transaction.atomic():
        refund = Refund.objects.select_for_update().get(pk=refund_id)
        if refund.status not in (Refund.Status.SUBMITTED, Refund.Status.PROCESSING):
            return SKIPPED
        refund.paystack_refund_id = refund.paystack_refund_id or answer.refund_id
        refund.checked_at = now
        status = answer.status
        if status == "processed":
            refund.status = Refund.Status.PROCESSED
            refund.processed_at = now
            _order_event(refund, Event.REFUND_PROCESSED)
            _log(refund, "processed")
        elif status == "processing" and refund.status == Refund.Status.SUBMITTED:
            refund.status = Refund.Status.PROCESSING
            _order_event(refund, Event.REFUND_PROCESSING)
            _log(refund, "processing")
        elif status not in ("pending", "processing", "failed", "needs-attention"):
            logger.warning("refund %s: Paystack sent a status we do not know", refund.pk)
        refund.save()
        outcome = refund.status
    if status == "failed":
        return _fail(refund_id, "paystack_failed_refund", give_up=False, now=now)
    if status == "needs-attention":
        return _fail(refund_id, "needs_bank_details", give_up=True, now=now)
    return outcome


def submit_refund(refund_id: int, client: PaystackClient, *, now: datetime | None = None) -> str:
    """Send one refund to Paystack. Safe to call from several runners at once: only one wins."""
    now = now or timezone.now()
    with transaction.atomic():  # claim it, and record that we are about to send
        refund = Refund.objects.select_for_update().select_related("payment").get(pk=refund_id)
        if refund.status != Refund.Status.REQUESTED:
            return SKIPPED
        if refund.next_attempt_at is not None and refund.next_attempt_at > now:
            return SKIPPED
        refund.status = Refund.Status.SUBMITTED
        refund.attempts += 1
        refund.submitted_at = now
        refund.last_error = ""
        refund.save()
        _order_event(refund, Event.REFUND_SUBMITTED)
        _log(refund, "sending", detail=f"attempt {refund.attempts}")
        reference, amount, currency = (
            refund.payment.reference,
            refund.amount_pesewas,
            refund.currency,
        )
        note = f"Refund {refund.reason} for order {refund.order_id}"
    try:  # no transaction is open while we wait for Paystack
        answer = client.create_refund(
            transaction_reference=reference,
            amount_pesewas=amount,
            currency=currency,
            merchant_note=note,
        )
    except PaystackError as error:
        # A refusal means asking again cannot help. Trouble reaching Paystack may or may not have
        # created the refund; asking again is safe because Paystack never refunds more than was
        # paid, and a refusal on the second ask sends it to a person to check.
        code = "paystack_unreachable" if error.retryable else "paystack_refused"
        return _fail(refund_id, code, give_up=not error.retryable, now=now)
    return _apply_answer(refund_id, answer, now)


def submit_due_refunds(client: PaystackClient, *, now: datetime | None = None, limit: int = 50):
    now = now or timezone.now()
    ids = list(
        Refund.objects.filter(status=Refund.Status.REQUESTED)
        .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
        .order_by("id")
        .values_list("pk", flat=True)[:limit]
    )
    return sum(submit_refund(refund_id, client, now=now) != SKIPPED for refund_id in ids)


# --- 3. following up ----------------------------------------------------------------------------


def sync_refund(refund_id: int, client: PaystackClient, *, now: datetime | None = None) -> str:
    """Ask Paystack how a sent refund is getting on, and record the answer."""
    now = now or timezone.now()
    refund = Refund.objects.get(pk=refund_id)
    if refund.status not in (Refund.Status.SUBMITTED, Refund.Status.PROCESSING):
        return SKIPPED
    if not refund.paystack_refund_id:
        return SKIPPED  # handled by mark_stuck_refunds
    answer = client.fetch_refund(refund.paystack_refund_id)
    return _apply_answer(refund_id, answer, now)


def sync_open_refunds(client: PaystackClient, *, now: datetime | None = None, limit: int = 100):
    now = now or timezone.now()
    recently = now - timedelta(minutes=int(option("poll_every_minutes")))
    ids = list(
        Refund.objects.filter(status__in=[Refund.Status.SUBMITTED, Refund.Status.PROCESSING])
        .exclude(paystack_refund_id="")
        .filter(Q(checked_at__isnull=True) | Q(checked_at__lt=recently))
        .order_by("id")
        .values_list("pk", flat=True)[:limit]
    )
    done = 0
    for refund_id in ids:
        try:
            done += sync_refund(refund_id, client, now=now) != SKIPPED
        except PaystackError:
            logger.warning("refund %s: could not ask Paystack, will try again", refund_id)
    return done


def mark_stuck_refunds(*, now: datetime | None = None) -> int:
    """A refund was sent and we never recorded Paystack's answer (we crashed or lost the answer).
    We cannot know whether it exists, so a person checks. Sending it again could refund twice."""
    now = now or timezone.now()
    cutoff = now - timedelta(minutes=int(option("stuck_after_minutes")))
    ids = list(
        Refund.objects.filter(status=Refund.Status.SUBMITTED, paystack_refund_id="")
        .filter(submitted_at__lt=cutoff)
        .values_list("pk", flat=True)
    )
    return sum(
        _fail(refund_id, "outcome_unknown", give_up=True, now=now) != SKIPPED for refund_id in ids
    )


def process_refunds(client: PaystackClient, *, now: datetime | None = None) -> RunSummary:
    """One round of everything above. Run every minute by Celery beat."""
    now = now or timezone.now()
    return RunSummary(
        queued=queue_refunds(now=now),
        submitted=submit_due_refunds(client, now=now),
        synced=sync_open_refunds(client, now=now),
        stuck=mark_stuck_refunds(now=now),
    )


# --- 4. people ----------------------------------------------------------------------------------


class NotAllowed(Exception):
    pass


def resolve_outside_system(refund_id: int, *, actor: str, note: str) -> None:
    """Staff record that a refund needing a person was made outside the system (for example in
    the Paystack dashboard, or by mobile money). Recorded with who, when and why."""
    note = " ".join(note.split())
    if not note:
        raise NotAllowed("say how the refund was made")
    now = timezone.now()
    with transaction.atomic():
        refund = Refund.objects.select_for_update().get(pk=refund_id)
        if refund.status != Refund.Status.MANUAL_RESOLUTION:
            raise NotAllowed("only a refund that needs a person can be resolved this way")
        refund.status = Refund.Status.PROCESSED
        refund.processed_at = now
        refund.resolved_by = actor
        refund.resolution_note = note[:300]
        _order_event(refund, Event.REFUND_RESOLVED_MANUALLY)
        _log(refund, "resolved_outside_system", actor=actor, detail=note)
        refund.save()


def overdue_refunds(*, now: datetime | None = None) -> list[int]:
    now = now or timezone.now()
    cutoff = now - timedelta(hours=int(option("overdue_after_hours")))
    return list(
        Refund.objects.exclude(status=Refund.Status.PROCESSED)
        .filter(created_at__lt=cutoff)
        .order_by("id")
        .values_list("pk", flat=True)
    )


def check_overdue_refunds(*, now: datetime | None = None) -> int:
    """Raise an alarm (an error in the logs, which reaches Sentry) for refunds unresolved after
    24 hours. The message holds ids only."""
    ids = overdue_refunds(now=now)
    if ids:
        logger.error("%s refunds are unresolved after 24 hours: ids %s", len(ids), ids[:20])
    return len(ids)
