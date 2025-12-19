import logging

def send_telegram_message(bot_token=None, chat_id=None, message=""):
    """
    Sends a Telegram message.
    You will add bot_token and chat_id later when you create accounts.
    """
    if not bot_token or not chat_id:
        logging.info("Telegram credentials not set. Message not sent.")
        return

    # Placeholder: code to send message using requests
    logging.info("Telegram message would be sent: %s", message)
