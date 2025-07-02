from dotenv import load_dotenv
from openai import OpenAI
import openai

load_dotenv()


def is_lead_relevant(message_text):
    try:
        openai_client = OpenAI(
            api_key=openai.api_key,
        )

        response = openai_client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": "You are a crypto business lead classifier."},
                {"role": "user",
                 "content": f"Does this message suggest the user may be interested business accounts, "
                            f"crypto infrastructure, or financial APIs? Respond"
                            f"only with 'yes' or 'no'. Message: {message_text}"}
            ]
        )

        answer = response.choices[0].message.content
        print(f"AI response: {answer}")

        return 'yes' in answer
    except Exception as e:
        print(f"AI analysis failed: {e}")
        return False


def generate_first_message(user_name: str, user_message: str):
    openai_client = OpenAI(
        api_key=openai.api_key,
    )

    response = openai_client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a crypto fintech sales specialist from P100, you have to send the first cold message to user. "
                    "You talk only in English. Your tone is casual and Telegram-style – relaxed, lowercase, minimal punctuation, no emojis. "
                    "Never start with 'hello', 'hi' or similar greetings. Mention naturally that you’re from P100. "
                    "Focus on crypto-friendly business accounts, IBANs, wallets, and Mastercards via API. "
                    "Keep it short, natural and human-like, no more than 3 sentences. Respond only with the message text."
                )
            },
            {
                "role": "user",
                "content": (
                    f"The user is interested in crypto-related services. Generate a first message "
                    f"to send to the user based on this message: {user_message}. User's name is {user_name}. "
                    f"Make it concise and engaging, focusing on crypto-friendly business accounts, IBANs, "
                    f"wallets, and Mastercards, all accessible via API. Respond only with the message text. "
                    f"Do not include any greetings or introductions. "
                    f"Keep it short, natural and human-like, no more than 3 sentences."
                )
            }
        ]
    )

    answer = response.choices[0].message.content
    print(f"AI response: {answer}")

    return answer
