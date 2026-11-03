class PricingError(ValueError):
    """The inputs cannot be priced (bad quantity, missing retail price, bad discount)."""
