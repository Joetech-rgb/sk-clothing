"""Inventory errors. Pure Python, no Django."""


class InventoryError(Exception):
    """Base class for every error the inventory services raise on purpose."""


class InsufficientStock(InventoryError):
    def __init__(self, variant_id: int | None, requested: int, available: int) -> None:
        super().__init__(f"requested {requested}, only {available} available")
        self.variant_id = variant_id
        self.requested = requested
        self.available = available


class ReservationNotActive(InventoryError):
    """The hold expired or was released, so it cannot become a sale."""

    def __init__(self, reservation_id: int, status: str) -> None:
        super().__init__(f"reservation {reservation_id} is {status}")
        self.reservation_id = reservation_id
        self.status = status


class IdempotencyConflict(InventoryError):
    """The same idempotency key was reused for a different request."""
