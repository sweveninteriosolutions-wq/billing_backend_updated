# app/utils/decimal_utils.py
from decimal import Decimal, ROUND_HALF_UP

TWOPLACES = Decimal("0.01")

def to_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def compute_balance(total_amount: Decimal, discounted_amount: Decimal, total_paid: Decimal) -> Decimal:
    total_amount = to_decimal(total_amount)
    discounted_amount = to_decimal(discounted_amount)
    total_paid = to_decimal(total_paid)
    balance = total_amount - discounted_amount - total_paid
    # business decision: negative balance (overpayments) not allowed here; callers should prevent overpayment
    return balance.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
