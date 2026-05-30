FROM python:3.12-slim

WORKDIR /app

# 先装依赖，利用层缓存
COPY pyproject.toml README.md ./
COPY mediamaid ./mediamaid
RUN pip install --no-cache-dir .

# 默认配置/状态放在 /config，媒体目录由 compose 挂载
VOLUME ["/config"]
ENV MEDIAMAID_CONFIG=/config/config.yaml

# 默认常驻监控；可在 compose 覆盖为 scan
ENTRYPOINT ["mediamaid"]
CMD ["watch", "-c", "/config/config.yaml"]
