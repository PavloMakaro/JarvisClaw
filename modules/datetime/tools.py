import asyncio
import datetime
import pytz
from typing import Dict, Any, Optional

# Constants
IRKUTSK_TZ = pytz.timezone("Asia/Irkutsk")
MOSCOW_TZ = pytz.timezone("Europe/Moscow")
UTC_TZ = pytz.UTC

# User preferences storage
_user_date_prefs = {
    "preferred_year": None,
    "year_source": "system_current",
    "user_confirmed": False,
}

async def get_current_time() -> str:
    """Get current time in human-readable format"""
    try:
        now = datetime.datetime.now()
        return now.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        return f"Error: {str(e)}"

async def get_irkutsk_time() -> Dict[str, Any]:
    """Get current time in Irkutsk timezone (UTC+8)"""
    try:
        utc_now = datetime.datetime.now(pytz.UTC)
        irkutsk_now = utc_now.astimezone(IRKUTSK_TZ)

        return {
            "date": irkutsk_now.strftime("%Y-%m-%d"),
            "time": irkutsk_now.strftime("%H:%M:%S"),
            "day_of_week": irkutsk_now.strftime("%A"),
            "full_datetime": irkutsk_now.strftime("%Y-%m-%d %H:%M:%S"),
            "is_working_day": irkutsk_now.weekday() < 5,
            "irkutsk_tz": "UTC+8",
        }
    except Exception as e:
        return {"error": str(e)}

async def get_weather(city: str) -> str:
    """Fetch weather from wttr.in"""
    try:
        import aiohttp

        url = f"https://wttr.in/{city}?format=3"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    text = await response.text()
                    return text.strip()
                else:
                    return f"Error: Could not fetch weather for {city}. Status: {response.status}"
    except Exception as e:
        return f"Error fetching weather: {str(e)}"

async def get_current_datetime_info() -> Dict[str, Any]:
    """Get detailed datetime information with timezone data"""
    try:
        now = datetime.datetime.now()
        irkutsk_now = datetime.datetime.now(IRKUTSK_TZ)

        info = {
            "system_date": now.strftime("%Y-%m-%d"),
            "system_time": now.strftime("%H:%M:%S"),
            "system_datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
            "irkutsk_date": irkutsk_now.strftime("%Y-%m-%d"),
            "irkutsk_time": irkutsk_now.strftime("%H:%M:%S"),
            "irkutsk_datetime": irkutsk_now.strftime("%Y-%m-%d %H:%M:%S"),
            "year": now.year,
            "month": now.month,
            "day": now.day,
            "weekday": now.strftime("%A"),
            "is_future": now.year > 2024,
            "timezone": "Asia/Irkutsk (UTC+8)",
            "note": "ВСЕГДА проверяйте эту дату перед ответом на вопросы о текущих событиях!",
        }

        return info
    except Exception as e:
        return {"error": str(e), "note": "Не удалось получить информацию о дате"}
