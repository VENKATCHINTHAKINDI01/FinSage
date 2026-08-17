"""Decimal-backed money.

v1 computed tax with floats throughout. The drift is invisible per operation
and unbounded across a return, and `0.1 + 0.2 != 0.3` is not a defensible
answer to "why is my tax ₹1 different from the department's".

`Money` wraps Decimal, quantises to paise, and refuses to interoperate with
float at all — you cannot accidentally introduce one.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Union

PAISE = Decimal("0.01")
RUPEE = Decimal("1")
TEN = Decimal("10")

Numeric = Union[int, str, Decimal, "Money"]


class Money:
    """An amount in Indian rupees, exact to the paisa.

    Immutable. Comparable. Hashable. Never a float.
    """

    __slots__ = ("_v",)

    def __init__(self, value: Numeric = 0) -> None:
        if isinstance(value, Money):
            v = value._v
        elif isinstance(value, float):  # type: ignore[unreachable]
            raise TypeError(
                "Money refuses float: binary floating point cannot represent "
                "rupees exactly. Pass an int, str or Decimal."
            )
        elif isinstance(value, Decimal):
            v = value
        elif isinstance(value, int | str):
            v = Decimal(value)
        else:
            raise TypeError(f"cannot build Money from {type(value).__name__}")
        object.__setattr__(self, "_v", v.quantize(PAISE, rounding=ROUND_HALF_UP))

    # ── access ──────────────────────────────────────────────────────────────

    @property
    def amount(self) -> Decimal:
        return self._v

    def __int__(self) -> int:
        return int(self._v)

    def __float__(self) -> float:
        raise TypeError(
            "refusing to convert Money to float — serialise with .to_json() "
            "or format with str()"
        )

    def to_json(self) -> str:
        """Serialise as a decimal string. Never as a JSON number: JSON numbers
        are IEEE 754 doubles at the other end, which reintroduces the problem."""
        return str(self._v)

    # ── arithmetic ──────────────────────────────────────────────────────────

    def _coerce(self, other: object) -> Decimal:
        if isinstance(other, Money):
            return other._v
        if isinstance(other, float):
            raise TypeError("cannot combine Money with float")
        if isinstance(other, int | str | Decimal):
            return Decimal(other)
        return NotImplemented  # type: ignore[return-value]

    def __add__(self, other: Numeric) -> Money:
        return Money(self._v + self._coerce(other))

    __radd__ = __add__

    def __sub__(self, other: Numeric) -> Money:
        return Money(self._v - self._coerce(other))

    def __rsub__(self, other: Numeric) -> Money:
        return Money(self._coerce(other) - self._v)

    def __mul__(self, factor: int | str | Decimal) -> Money:
        if isinstance(factor, float):
            raise TypeError(
                "cannot multiply Money by float — express rates as "
                "Decimal('0.05'), not 0.05"
            )
        return Money(self._v * Decimal(factor))

    __rmul__ = __mul__

    def __truediv__(self, divisor: int | str | Decimal) -> Money:
        if isinstance(divisor, float):
            raise TypeError("cannot divide Money by float")
        return Money(self._v / Decimal(divisor))

    def __neg__(self) -> Money:
        return Money(-self._v)

    def __abs__(self) -> Money:
        return Money(abs(self._v))

    # ── comparison ──────────────────────────────────────────────────────────

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Money):
            return self._v == other._v
        if isinstance(other, int | Decimal):
            return self._v == Decimal(other)
        return NotImplemented

    def __lt__(self, other: Numeric) -> bool:
        return self._v < self._coerce(other)

    def __le__(self, other: Numeric) -> bool:
        return self._v <= self._coerce(other)

    def __gt__(self, other: Numeric) -> bool:
        return self._v > self._coerce(other)

    def __ge__(self, other: Numeric) -> bool:
        return self._v >= self._coerce(other)

    def __hash__(self) -> int:
        return hash(self._v)

    def __bool__(self) -> bool:
        return self._v != 0

    # ── rounding ────────────────────────────────────────────────────────────

    def to_rupees(self) -> Money:
        return Money(self._v.quantize(RUPEE, rounding=ROUND_HALF_UP))

    def round_288a(self) -> Money:
        """Round total income to the nearest ₹10.

        Income-tax Act 2025 (legacy s.288A). Applied to total income before
        the slab computation.
        """
        return Money((self._v / TEN).quantize(RUPEE, rounding=ROUND_HALF_UP) * TEN)

    def round_288b(self) -> Money:
        """Round tax payable or refundable to the nearest ₹10.

        Income-tax Act 2025 (legacy s.288B). Applied once, at the very end.
        Published worked examples usually omit this, so the engine reports both
        the exact figure and the statutory rounded one rather than silently
        picking whichever matches a given source.
        """
        return Money((self._v / TEN).quantize(RUPEE, rounding=ROUND_HALF_UP) * TEN)

    def clamp_non_negative(self) -> Money:
        """Tax is never negative. A deduction larger than income yields zero,
        not a rebate."""
        return self if self._v >= 0 else ZERO

    # ── display ─────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"Money('{self._v}')"

    def __str__(self) -> str:
        return f"₹{self.indian_format()}"

    def indian_format(self) -> str:
        """Lakh/crore digit grouping: 1234567.00 -> '12,34,567'."""
        v = self._v.quantize(RUPEE, rounding=ROUND_HALF_UP)
        sign = "-" if v < 0 else ""
        digits = str(abs(v).to_integral_value())

        if len(digits) <= 3:
            return sign + digits
        head, tail = digits[:-3], digits[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        return sign + ",".join([*parts, tail])


ZERO = Money(0)


def rupees(value: Numeric) -> Money:
    """Readable constructor: `rupees(1_200_000)`."""
    return Money(value)


def rate(value: str) -> Decimal:
    """A tax rate, always from a string so it is exact.

    `rate("0.05")` is 5%. `Decimal(0.05)` would be
    0.05000000000000000277555756156289135105907917022705078125.
    """
    return Decimal(value)


def pct_of(amount: Money, r: Decimal) -> Money:
    return amount * r


def format_rate(r: Decimal) -> str:
    """Render a rate as a percentage for display.

    `Decimal.normalize()` turns 10 into '1E+1', which is correct and useless:
    a worksheet line reading "@ 1E+1%" is not something you show a taxpayer.
    """
    pct = r * 100
    quantised = pct.quantize(Decimal("0.01")).normalize()
    if quantised == quantised.to_integral_value():
        return f"{int(quantised)}"
    return f"{quantised}"


def minimum(*values: Money) -> Money:
    return min(values)


def maximum(*values: Money) -> Money:
    return max(values)
