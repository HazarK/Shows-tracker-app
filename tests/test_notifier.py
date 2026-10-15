import httpx
import pytest

from tvtracker.bot.notifier import TelegramNotifier, TelegramSendError


def _notifier(handler) -> TelegramNotifier:
    return TelegramNotifier(
        "super-secret-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_send_posts_chat_and_text():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read().decode()
        assert "super-secret-token" in str(request.url)
        return httpx.Response(200, json={"ok": True, "result": {}})

    _notifier(handler).send(5, "hello")

    assert '"chat_id": 5' in str(seen["body"]) or '"chat_id":5' in str(seen["body"])
    assert "hello" in str(seen["body"])


def test_send_failure_does_not_include_the_bot_token():
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        raise httpx.ConnectError("down")

    with pytest.raises(TelegramSendError) as exc_info:
        _notifier(handler).send(1, "hi")

    assert exc_info.value.__cause__ is None
    assert "super-secret-token" not in str(exc_info.value)


def test_telegram_error_response_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(400, json={"ok": False, "description": "bad chat"})

    with pytest.raises(TelegramSendError) as exc_info:
        _notifier(handler).send(1, "hi")

    assert "super-secret-token" not in str(exc_info.value)
