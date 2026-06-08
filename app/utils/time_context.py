from datetime import datetime
from zoneinfo import ZoneInfo


def get_time_context() -> str:
    timezone = "America/Sao_Paulo"
    now = datetime.now(ZoneInfo(timezone))

    current_datetime = now.strftime("%Y-%m-%d %H:%M:%S")

    return (
        f"Current datetime: {current_datetime}\n"
        f"Timezone: {timezone}"
    )