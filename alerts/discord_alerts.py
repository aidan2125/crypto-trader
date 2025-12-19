import logging

def send_discord_message(webhook_url=None, message=""):
    """
    Sends a message to a Discord channel via webhook.
    Webhook URL will be added later.
    """
    if not webhook_url:
        logging.info("Discord webhook not set. Message not sent.")
        return

    # Placeholder: code to send message
    logging.info("Discord message would be sent: %s", message)
