"""Money as whole pesewas. Never floats. GHS only (CLAUDE.md section 4)."""

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Money:
    pesewas: int

    def __post_init__(self) -> None:
        if isinstance(self.pesewas, bool) or not isinstance(self.pesewas, int):
            raise TypeError("Money takes whole pesewas as an int, never a float")

    def __add__(self, other: object) -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self.pesewas + other.pesewas)

    def times(self, quantity: int) -> "Money":
        if isinstance(quantity, bool) or not isinstance(quantity, int):
            raise TypeError("quantity must be an int")
        return Money(self.pesewas * quantity)

    def __str__(self) -> str:
        cedis, pesewas = divmod(abs(self.pesewas), 100)
        sign = "-" if self.pesewas < 0 else ""
        return f"{sign}GHS {cedis:,}.{pesewas:02d}"
