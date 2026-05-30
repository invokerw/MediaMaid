"""Bark 通知器：推送到 iOS Bark App。演示「丢一个文件即新增插件」。"""

from __future__ import annotations

import httpx
from pydantic import BaseModel

from ...logging_conf import get_logger
from ...models import Event
from ..base import Notifier
from ..registry import register

log = get_logger(__name__)


class BarkConfig(BaseModel):
    # 形如 https://api.day.app/<your-key>
    url: str
    timeout: float = 10.0


@register
class BarkNotifier(Notifier):
    name = "bark"
    ConfigModel = BarkConfig

    def notify(self, event: Event) -> None:
        try:
            httpx.get(
                f"{self.config.url.rstrip('/')}/MediaMaid/{event.message}",
                timeout=self.config.timeout,
            )
        except httpx.HTTPError as e:
            log.warning("bark 推送失败: %s", e)
