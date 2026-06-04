FROM python:3.12-slim

WORKDIR /app

# 先装依赖，利用层缓存。含 web(FastAPI/uvicorn) 与 plugins(feedparser/qbittorrent 等)。
# 前端构建产物已随 mediamaid/web/static 提交，镜像无需 Node。
COPY pyproject.toml README.md ./
COPY mediamaid ./mediamaid
RUN pip install --no-cache-dir ".[web,plugins]"

# 默认配置/状态放在 /config，媒体目录由 compose 挂载
VOLUME ["/config"]
ENV MEDIAMAID_CONFIG=/config/config.yaml

# 默认常驻监控；可在 compose 覆盖为 scan
ENTRYPOINT ["mediamaid"]
CMD ["watch", "-c", "/config/config.yaml"]
