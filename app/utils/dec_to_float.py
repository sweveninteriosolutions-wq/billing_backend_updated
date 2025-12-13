from decimal import Decimal

def decimal_to_float(obj):
    """Recursively convert Decimals to floats in dicts/lists"""
    if isinstance(obj, list):
        return [decimal_to_float(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        return float(obj)
    return obj
