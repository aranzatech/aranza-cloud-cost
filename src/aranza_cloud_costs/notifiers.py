from __future__ import annotations

import json
from abc import ABC, abstractmethod
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import CloudCostConfig
from .models import Alert


class NotificationError(RuntimeError):
    """Raised when a notification destination rejects a message."""


def format_alert(alert: Alert) -> str:
    icon = "🚨" if alert.exceeded else "⚠️"
    return (
        f"{icon} Cloud budget alert: {alert.provider.value.upper()} is at "
        f"{alert.utilization * 100:.1f}% of its budget "
        f"({alert.amount} / {alert.budget} {alert.currency}; threshold {alert.threshold * 100:.0f}%)."
    )


class Notifier(ABC):
    @abstractmethod
    def send(self, alert: Alert) -> None:
        """Send one budget alert."""


class SlackNotifier(Notifier):
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    def send(self, alert: Alert) -> None:
        _post_json(self.webhook_url, {"text": format_alert(alert)})


class TelegramNotifier(Notifier):
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, alert: Alert) -> None:
        _post_json(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            {"chat_id": self.chat_id, "text": format_alert(alert)},
        )


def configured_notifiers(config: CloudCostConfig) -> list[Notifier]:
    targets: list[Notifier] = []
    if config.slack_enabled and config.slack_webhook_url:
        targets.append(SlackNotifier(config.slack_webhook_url))
    if config.telegram_enabled and config.telegram_bot_token and config.telegram_chat_id:
        targets.append(TelegramNotifier(config.telegram_bot_token, config.telegram_chat_id))
    return targets


def _post_json(url: str, payload: dict[str, str]) -> None:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:  # nosec B310 - configured webhook endpoint.
            if response.status >= 400:
                raise NotificationError(f"Notification endpoint returned HTTP {response.status}.")
    except (HTTPError, URLError) as exc:
        raise NotificationError(f"Notification delivery failed: {exc}") from exc
