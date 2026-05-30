# MediaMaid

自动化媒体整理工具。完整流水线：

> **监控源目录 → 识别资源 → 刮削元数据 → 复制/硬链接/移动到媒体库**

典型场景：PT/BT 下载完成后，自动把杂乱命名的影视文件识别、刮削并按媒体库规范（Jellyfin/Plex/Emby 可直接识别）整理到媒体库，硬链接保留原文件做种。

## 特性

- **监控**：watchdog 实时监听 + 文件稳定性检测（避免处理下载中的半成品）+ 定时兜底全量重扫
- **识别**：基于 [guessit](https://github.com/guessit-io/guessit) 解析电影/剧集的标题、年份、季、集
- **刮削**：TMDB 电影/剧集元数据，带置信度匹配（低于阈值不乱命名）与进程内缓存；无 API key 时降级为仅按文件名整理
- **落地**：硬链接（跨盘自动回退复制）/ 复制（临时文件+原子改名）/ 移动；冲突可配 skip/overwrite/rename
- **命名**：默认 Jellyfin 规范，模板可配
- **状态**：SQLite 去重、记录映射、支持 `undo` 回滚
- **可选**：生成 `.nfo` + 下载封面/fanart
- **插件化**：刮削器 / 订阅器 / 下载器 / 通知器 全部可插拔，丢一个文件即生效
- **全自动闭环**：`run` 一个守护进程把 订阅→下载→完成→整理→通知 串成一条龙

## 安装

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e .
```

## 使用

```bash
cp config.example.yaml config.yaml   # 编辑源目录、媒体库、TMDB key

mediamaid scan --dry-run             # 预览整理计划，不落地
mediamaid scan                       # 执行一次整理
mediamaid watch                      # 常驻监控源目录并整理
mediamaid run                        # 全自动闭环守护(订阅→下载→整理→通知 一条龙)
mediamaid status                     # 查看最近处理记录
mediamaid undo                       # 回滚最近一批
mediamaid identify <文件路径>         # 调试单个文件的识别结果
mediamaid plugins                    # 列出所有已发现的插件
mediamaid subscribe [--loop]         # 订阅器发现新资源 → 下载器
mediamaid web                        # 启动 Web 管理界面(默认 127.0.0.1:8500)
```

## Web 界面

```bash
pip install -e '.[web]'              # 安装 Web 依赖(FastAPI/uvicorn)
mediamaid web -c config.yaml         # 浏览器打开 http://127.0.0.1:8500
```

轻量服务端渲染（FastAPI + Jinja2，无前端构建）。提供：
- **仪表盘**：已整理/跳过/失败计数、最近记录，一键触发扫描（含 dry-run 预览）与订阅
- **记录**：处理历史，可按状态过滤
- **插件**：各类别已发现插件、哪些已启用
- **配置**：当前配置只读查看

可与 `mediamaid run` 守护进程同时运行（共享 SQLite，已开 WAL）。

## 配置

见 `config.example.yaml`，含逐项注释。

## 插件系统

四类模块均可插拔，由 `config.yaml` 的 `plugins:` 段按名启用：

| 类别 | 接口方法 | 内置示例 |
|---|---|---|
| `scraper` 刮削器 | `scrape(item) -> MediaInfo` | `tmdb`, `null` |
| `subscriber` 订阅器 | `fetch() -> [Release]` | `rss` |
| `downloader` 下载器 | `add(release) -> bool` | `qbittorrent` |
| `notifier` 通知器 | `notify(event)` | `log`, `webhook` |

> RSS / qBittorrent 需 `pip install 'mediamaid[plugins]'`。

### 全自动闭环（`mediamaid run`）

一个常驻进程同时跑两件事，串成闭环：

```
订阅器 fetch ─► 去重 ─► 下载器 add ─► (下载到源目录)
                                          │
源目录监控 ◄──────────────────────────────┘
   │ 文件稳定后
   └─► 识别 ─► 刮削 ─► 整理入库 ─► 通知器
```

衔接靠下载器把文件存进被监控的 `source_dirs`（qBittorrent 配 `save_path`）。
若下载客户端保存路径不在监控目录，可开 `poll_completed: true`，守护进程会轮询
下载器的「已完成」任务并主动整理（重复处理由状态库去重兜底）。

### 写一个插件

在 `mediamaid/plugins/<类别>/` 下新建一个 `.py`，继承对应基类并 `@register`：

```python
# mediamaid/plugins/notifier/bark.py
import httpx
from pydantic import BaseModel
from ...models import Event
from ..base import Notifier
from ..registry import register

class BarkConfig(BaseModel):
    url: str

@register
class BarkNotifier(Notifier):
    name = "bark"
    ConfigModel = BarkConfig
    def notify(self, event: Event) -> None:
        httpx.get(f"{self.config.url}/{event.message}")
```

保存即被 `mediamaid plugins` 发现，配置里写 `notifier: [{name: bark, config: {url: ...}}]` 即启用。
重依赖请在方法内**惰性 import**。外部 pip 包也可经 `entry_points` 组 `mediamaid.plugins` 提供。

## 部署

**Docker**（编辑 `docker-compose.yml` 的挂载与 `config/config.yaml`）：

```bash
docker compose up -d        # 常驻监控
```

> ⚠️ 源目录与媒体库需挂在同一挂载点下，否则跨设备无法硬链接（自动回退复制）。

**systemd**（见 `deploy/mediamaid.service`，按需改用户/路径）：

```bash
sudo cp deploy/mediamaid.service /etc/systemd/system/
sudo systemctl enable --now mediamaid
```

## 开发

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

## 架构

```
                    Daemon(daemon.py) 闭环编排
   订阅器 ─► 下载器        监控 ─► 识别 ─► 刮削 ─► 整理 ─► 通知器
   subscriber/ downloader/  watcher  identify  scraper/  organizer  notifier/
   └── subscribe.py ──┘       └──────── pipeline.py 串联 ────────┘
                插件框架 plugins/{base,registry}.py
        StateStore(store.py) / Config(config.py) / Naming / Transfer
```

插件按目录自动发现：`mediamaid/plugins/<类别>/*.py` 中 `@register` 的类即被注册。
