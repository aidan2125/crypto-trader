import os
from unittest.mock import Mock


def test_send_discord_message_posts(monkeypatch):
    """Verify that `send_discord_message` posts to the webhook when configured.

    This test patches `alerts.discord_alerts.requests.post` to avoid network I/O
    and asserts the function returns True and that `post` was called with the
    expected arguments.
    """
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.com/webhook")

    # prepare a fake response object
    mock_resp = Mock()
    mock_resp.status_code = 204
    mock_resp.text = ""
    mock_resp.raise_for_status = Mock()

    # mock requests.post to return the fake response
    mock_post = Mock(return_value=mock_resp)
    monkeypatch.setattr("alerts.discord_alerts.requests", Mock(post=mock_post))

    # import the module under test and call the function
    from alerts import discord_alerts

    ok = discord_alerts.send_discord_message("unit test message")

    assert ok is True
    mock_post.assert_called_once_with(
        "https://example.com/webhook",
        json={"content": "unit test message"},
        timeout=10,
    )
