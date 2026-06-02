"""日志通知器：把事件写入日志（零依赖，默认启用）。"""

from __future__ import annotations

from ...logging_conf import get_logger
from ...models import Event
from ..base import Notifier
from ..registry import register

log = get_logger("mediamaid.notify")


@register
class LogNotifier(Notifier):
    name = "log"
    description = "日志通知器，把事件写入日志（零依赖，默认启用）"

    def notify(self, event: Event) -> None:
        if event.type == "error":
            log.error("[%s] %s", event.type, event.message)
        else:
            log.info("[%s] %s", event.type, event.message)
