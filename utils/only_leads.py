from utils.database import get_lead


def run_only_for_leads(func):
    """
    Decorator to run a function only for existing leads.

    If the chat ID is not in the leads list, the function will not run.
    """

    async def wrapper(event, *args, **kwargs):
        chat_id = str(event.chat_id)

        if get_lead(chat_id):
            return await func(event, *args, **kwargs)
        else:
            print(f"Chat ID {chat_id} is not a lead. Skipping...")
            return None

    return wrapper
