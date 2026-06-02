#!/usr/bin/env bash
# 重启 MediaMaid Web 服务。
# 默认行为：重新构建前端 → 停掉旧进程 → 后台拉起新进程 → 健康检查。
#
# 用法:
#   scripts/restart-web.sh                 # 构建前端并重启(默认)
#   scripts/restart-web.sh --no-build      # 跳过前端构建，仅重启后端
#   scripts/restart-web.sh --foreground    # 前台运行(Ctrl-C 退出，便于看日志)
#
# 可用环境变量覆盖默认值:
#   CONFIG  配置文件路径   (默认 demo/config.yaml)
#   HOST    监听地址       (默认 0.0.0.0)
#   PORT    监听端口       (默认 8500)
#   PYTHON  Python 解释器  (默认 .venv/bin/python)
set -euo pipefail

# 切到仓库根目录(脚本所在目录的上一级)
cd "$(dirname "$0")/.."

CONFIG="${CONFIG:-demo/config.yaml}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8500}"
PYTHON="${PYTHON:-.venv/bin/python}"
LOG="${LOG:-/tmp/mediamaid_web.log}"

BUILD=1
FOREGROUND=0
for arg in "$@"; do
  case "$arg" in
    --no-build)   BUILD=0 ;;
    --foreground) FOREGROUND=1 ;;
    -h|--help)    sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "未知参数: $arg" >&2; exit 2 ;;
  esac
done

# 1) 构建前端(输出到 mediamaid/web/static)
if [[ "$BUILD" == 1 ]]; then
  echo "==> 构建前端…"
  ( cd mediamaid/web/frontend && npm run build )
else
  echo "==> 跳过前端构建 (--no-build)"
fi

# 2) 停掉占用端口的旧进程
echo "==> 停止旧服务 (port $PORT)…"
PIDS="$(pgrep -f "mediamaid.cli web .*--port ${PORT}" || true)"
if [[ -n "$PIDS" ]]; then
  # shellcheck disable=SC2086
  kill $PIDS 2>/dev/null || true
  sleep 1
  # 仍存活则强杀
  for pid in $PIDS; do
    if kill -0 "$pid" 2>/dev/null; then kill -9 "$pid" 2>/dev/null || true; fi
  done
  echo "    已停止: $PIDS"
else
  echo "    无运行中的实例"
fi

# 3) 拉起新进程
CMD=("$PYTHON" -m mediamaid.cli web --config "$CONFIG" --host "$HOST" --port "$PORT")
if [[ "$FOREGROUND" == 1 ]]; then
  echo "==> 前台启动: ${CMD[*]}"
  exec "${CMD[@]}"
fi

echo "==> 后台启动: ${CMD[*]}"
nohup "${CMD[@]}" > "$LOG" 2>&1 &
NEW_PID=$!
echo "    PID=$NEW_PID  日志=$LOG"

# 4) 健康检查
echo "==> 健康检查…"
for i in $(seq 1 15); do
  code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/" || true)"
  if [[ "$code" == "200" ]]; then
    echo "    OK — http://${HOST}:${PORT}/ (HTTP 200)"
    exit 0
  fi
  sleep 1
done

echo "    启动检查超时，请查看日志: $LOG" >&2
tail -n 20 "$LOG" >&2 || true
exit 1
