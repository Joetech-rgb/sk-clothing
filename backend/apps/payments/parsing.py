"""Extract the few fields we keep from a Paystack event. Pure Python, no Django imports."""

from dataclasses import dataclass

MAX_EVENT_TYPE = 64
MAX_REFERENCE = 100


@dataclass(frozen=True)
class ParsedEvent:
    event_type: str
    reference: str
    amount: int | None  # integer pesewas, exactly as Paystack sends it
    currency: str

    @property
    def dedupe_key(self) -> str:
        return f"{self.event_type}:{self.reference}"


def parse_event(payload: object) -> ParsedEvent | None:
    """Return the event, or None if it is not a shape we can de-duplicate."""
    if not isinstance(payload, dict):
        return None
    event_type = payload.get("event")
    data = payload.get("data")
    if not isinstance(event_type, str) or not isinstance(data, dict):
        return None
    reference = data.get("reference")
    if not isinstance(reference, str) or not reference:
        return None
    if not event_type or len(event_type) > MAX_EVENT_TYPE or len(reference) > MAX_REFERENCE:
        return None

    amount = data.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, int):
        amount = None
    currency = data.get("currency")
    if not isinstance(currency, str) or len(currency) > 3:
        currency = ""
    return ParsedEvent(event_type, reference, amount, currency)
