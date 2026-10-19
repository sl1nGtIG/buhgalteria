def fmt_money(value: float | None) -> str:
    """5000.5 → «5 000,5 ₽»."""
    if value is None:
        return "—"
    text = f"{value:,.2f}".rstrip("0").rstrip(".").replace(",", " ").replace(".", ",")
    return f"{text} ₽"
