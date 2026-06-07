from datetime import datetime


def fmt_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%Y-%m-%d %I:%M %p")


def fmt_date(value) -> str:
    if value is None:
        return "-"
    return value.strftime("%Y-%m-%d")
