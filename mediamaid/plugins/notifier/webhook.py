"""Webhook 通知器：把事件 POST 成 JSON 到指定 URL。"""

from __future__ import annotations

import httpx
from pydantic import BaseModel

from ...logging_conf import get_logger
from ...models import Event
from ..base import Notifier
from ..registry import register

log = get_logger(__name__)


class WebhookConfig(BaseModel):
    url: str
    timeout: float = 10.0
    # 仅推送这些事件类型；空表示全部
    events: list[str] = []


@register
class WebhookNotifier(Notifier):
    name = "webhook"
    description = "Webhook 通知器，把事件 POST 成 JSON 到指定 URL"
    ConfigModel = WebhookConfig

    def notify(self, event: Event) -> None:
        cfg: WebhookConfig = self.config
        if cfg.events and event.type not in cfg.events:
            return
        payload = {
            "type": event.type,
            "message": event.message,
            "title": event.info.title if event.info else (event.item.title if event.item else None),
            "dest": str(event.dest) if event.dest else None,
        }
        try:
            httpx.post(cfg.url, json=payload, timeout=cfg.timeout)
        except httpx.HTTPError as e:
            log.warning("webhook 推送失败 %s: %s", cfg.url, e)
