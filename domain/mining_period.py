from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))


def scheduled_period(now, hours, minutes):
    now = (now or datetime.now(JST)).astimezone(JST)
    boundaries = (
        (now - timedelta(days=day)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        for day in (0, 1) for hour in hours for minute in minutes
    )
    return max(boundary for boundary in boundaries if boundary <= now).isoformat()
