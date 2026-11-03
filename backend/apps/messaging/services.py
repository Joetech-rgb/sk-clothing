from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.academics.results import class_students
from apps.students.models import Classroom, Student

from .models import (AuditEntry, Discount, FeeStructureItem, Instalment, Invoice, InvoiceLine, Payment,
                     PaymentAllocation)

ZERO = Decimal("0.00")
TWO = Decimal("0.01")


class FinanceError(Exception):
    pass


class DuplicateWarning(FinanceError):
    # NOTE: this is a subclass of FinanceError, so in views `except DuplicateWarning` must come BEFORE `except FinanceError`.
    pass


def audit(user, action, detail=""):
    AuditEntry.objects.create(user=user if getattr(user, "pk", None) else None, action=action, detail=detail[:300])


def money(v):
    return Decimal(str(v)).quantize(TWO, ROUND_HALF_UP)  # FIX: str() avoids binary-float noise for float input


def next_number(model, field, prefix):
    last = model.objects.filter(**{f"{field}__startswith": prefix}).order_by(f"-{field}").first()
    n = int(getattr(last, field).split("-")[-1]) + 1 if last else 1
    return f"{prefix}{n:05d}"


def invoice_amounts(invoices):
    """Attach .total, .paid and .balance to each invoice (reversed payments are ignored)."""
    invoices = list(invoices)
    ids = [i.pk for i in invoices]
    totals = dict(InvoiceLine.objects.filter(invoice_id__in=ids).order_by().values_list("invoice_id").annotate(s=Sum("amount")))
    paid = dict(PaymentAllocation.objects.filter(invoice_id__in=ids, payment__reversed_at__isnull=True)
                .order_by().values_list("invoice_id").annotate(s=Sum("amount")))
    for inv in invoices:
        inv.total, inv.paid = totals.get(inv.pk, ZERO), paid.get(inv.pk, ZERO)
        inv.balance = inv.total - inv.paid
    return invoices


def student_outstanding(student):
    invs = invoice_amounts(Invoice.objects.filter(student=student).select_related("term__academic_year"))
    return sum((i.balance for i in invs), ZERO), invs


def term_summary(term):
    invs = invoice_amounts(Invoice.objects.filter(term=term))
    expected = sum((i.total for i in invs), ZERO)
    collected = sum((i.paid for i in invs), ZERO)
    return {"expected": expected, "collected": collected, "outstanding": expected - collected,
            "rate": int(collected * 100 / expected) if expected else 0, "invoices": len(invs)}


def is_new_student(student, term):
    return term.start_date - timedelta(days=60) <= student.admission_date <= term.end_date


def generate_invoices(term, rooms, user, dummy=False):
    created = skipped = no_structure = 0
    for room in rooms:
        items = list(FeeStructureItem.objects.filter(term=term, level=room.level, fee_type__is_active=True)
                     .select_related("fee_type").order_by("fee_type__order", "fee_type_id"))
        for st in class_students(room, term):
            if Invoice.objects.filter(student=st, term=term).exists():
                skipped += 1
                continue
            lines = [i for i in items if not i.fee_type.new_students_only or is_new_student(st, term)]
            if not lines:
                no_structure += 1
                continue
            with transaction.atomic():
                inv = Invoice.objects.create(
                    number=next_number(Invoice, "number", f"INV-{term.academic_year.start_date.year}-"),
                    student=st, term=term, classroom=room, created_by=user, is_dummy=dummy)
                gross = ZERO
                by_type = {}
                for it in lines:
                    InvoiceLine.objects.create(invoice=inv, description=it.fee_type.name, amount=it.amount,
                                               kind="fee", fee_type=it.fee_type, created_by=user)
                    gross += it.amount
                    by_type[it.fee_type_id] = by_type.get(it.fee_type_id, ZERO) + it.amount
                off = ZERO
                for d in Discount.objects.filter(student=st, status="approved", is_active=True).filter(
                        Q(term__isnull=True) | Q(term=term)).select_related("fee_type"):
                    base = by_type.get(d.fee_type_id, ZERO) if d.fee_type_id else gross
                    value = money(base * d.percent / 100) if d.percent else min(d.amount or ZERO, base)
                    value = min(value, gross - off)
                    if value > 0:
                        label = d.fee_type.name if d.fee_type_id else "all fees"
                        InvoiceLine.objects.create(invoice=inv, description=f"{d.get_kind_display()} ({label})" + (f": {d.reason}" if d.reason else ""),
                                                   amount=-value, kind="discount", created_by=user)
                        off += value
                created += 1
    if created:
        audit(user, "Invoices generated", f"{term}: {created} created")
    return {"created": created, "skipped": skipped, "no_structure": no_structure}


def record_payment(student, amount, method, reference, paid_on, user, invoice=None, note="", confirm_duplicate=False, dummy=False):
    amount = money(amount)
    if amount <= 0:
        raise FinanceError("Enter an amount greater than zero.")
    reference = (reference or "").strip()
    # FIX: balances, duplicate checks and the insert now happen in ONE transaction. Before, the balance was
    # read first and the payment written later, so two cashiers could both pass the "not more than balance" check.
    with transaction.atomic():
        Student.objects.select_for_update().filter(pk=student.pk).first()  # serialises per student on PostgreSQL/MySQL
        outstanding = [i for i in invoice_amounts(Invoice.objects.filter(student=student).select_related("term__academic_year")
                                                  .order_by("term__start_date", "id")) if i.balance > 0]
        if invoice is not None:
            targets = [i for i in outstanding if i.pk == invoice.pk]
            if not targets:
                raise FinanceError("That invoice has no balance to pay.")
        else:
            targets = outstanding
        total_due = sum((i.balance for i in targets), ZERO)
        if not targets:
            raise FinanceError(f"{student.full_name} has no outstanding balance.")
        if amount > total_due:
            raise FinanceError(f"The amount ({amount:,.2f}) is more than the outstanding balance ({total_due:,.2f}).")
        if reference and Payment.objects.filter(method=method, reference__iexact=reference, reversed_at__isnull=True).exists():
            raise FinanceError(f"A {method} payment with reference '{reference}' is already recorded (duplicate).")
        if not confirm_duplicate and Payment.objects.filter(student=student, amount=amount, paid_on=paid_on, reversed_at__isnull=True).exists():
            raise DuplicateWarning("A payment of the same amount for this student on this date already exists.")
        pay = None
        for attempt in range(3):  # FIX: retry if two receipts were given the same number at the same moment
            try:
                with transaction.atomic():
                    pay = Payment.objects.create(
                        receipt_no=next_number(Payment, "receipt_no", f"RC-{paid_on.year}-"), student=student, amount=amount,
                        method=method, reference=reference, paid_on=paid_on, note=note, received_by=user, is_dummy=dummy)
                break
            except IntegrityError:
                if attempt == 2:
                    raise FinanceError("Could not allocate a receipt number. Please try again.")
        remaining = amount
        for inv in targets:
            if remaining <= 0:
                break
            take = min(remaining, inv.balance)
            PaymentAllocation.objects.create(payment=pay, invoice=inv, amount=take)
            remaining -= take
    audit(user, "Payment recorded", f"{pay.receipt_no}: GHS {amount} from {student.student_id} ({method})")
    return pay


def reverse_payment(payment, user, reason):
    reason = (reason or "").strip()
    if not reason:  # FIX: a reversal without a reason is not auditable
        raise FinanceError("A reason is required to reverse a payment.")
    with transaction.atomic():
        # FIX: re-read inside the transaction so a stale page cannot reverse the same payment twice
        p = Payment.objects.select_for_update().get(pk=payment.pk)
        if p.reversed_at:
            raise FinanceError("This payment has already been reversed.")
        p.reversed_at, p.reversed_by, p.reversal_reason = timezone.now(), user, reason[:255]
        p.save()
    payment.reversed_at, payment.reversed_by, payment.reversal_reason = p.reversed_at, p.reversed_by, p.reversal_reason
    audit(user, "Payment reversed", f"{payment.receipt_no}: {reason}")


def create_plan(invoice, count, first_due, every_days):
    if count < 2:
        raise FinanceError("An instalment plan needs at least 2 instalments.")
    invoice = invoice_amounts([invoice])[0]
    if invoice.balance <= 0:
        raise FinanceError("This invoice is fully paid.")
    # plan covers the whole invoice total; instalments already covered by payments show as paid
    each = money(invoice.total / count)
    with transaction.atomic():
        invoice.instalments.all().delete()
        for n in range(1, count + 1):
            amt = each if n < count else invoice.total - each * (count - 1)
            Instalment.objects.create(invoice=invoice, number=n, due_date=first_due + timedelta(days=every_days * (n - 1)), amount=amt)


def instalment_status(invoice, paid):
    """For each instalment: paid / part-paid / overdue / upcoming, using the cumulative amount paid so far."""
    today = timezone.localdate()
    rows, cumulative = [], ZERO
    for ins in invoice.instalments.all():
        cumulative += ins.amount
        if paid >= cumulative:
            status = "Paid"
        elif ins.due_date < today:
            status = "Overdue"
        elif paid > cumulative - ins.amount:
            status = "Part-paid"
        else:
            status = "Upcoming"
        rows.append({"i": ins, "status": status})
    return rows
