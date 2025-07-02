import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


def run_only_in_working_hours(func):
    """
    Decorator to run a function only during specified working hours.

    Working hours are defined by environment variables:
    - WORKING_HOUR_START: Start time in HH:MM format (default is 09:00)
    - WORKING_HOUR_END: End time in HH:MM format (default is 17:00)

    If current time is outside working hours, the function will not run.
    """

    def wrapper(*args, **kwargs):
        if is_working_hour():
            return func(*args, **kwargs)
        else:
            print("Function not executed: outside of working hours.")
            return None

    return wrapper


def is_working_hour() -> bool:

    """
    Check if the current time is within specified working hours.

    Returns:
        bool: True if current time is within working hours, False otherwise.
    """

    now = datetime.now()

    start_hour = os.getenv("WORKING_HOUR_START", "09:00")
    end_hour = os.getenv("WORKING_HOUR_END", "17:00")

    start_time = datetime.strptime(start_hour, "%H:%M").time()
    end_time = datetime.strptime(end_hour, "%H:%M").time()

    # Check if current time is within working hours
    return start_time <= now.time() <= end_time
