# MediaMaid

自动化媒体整理工具。完整流水线：

> **监控源目录 → 识别资源 → 刮削元数据 → 复制/硬链接/移动到媒体库**

典型场景：PT/BT 下载完成后，自动把杂乱命名的影视文件识别、刮削并按媒体库规范（Jellyfin/Plex/Emby 可直接识别）整理到媒体库，硬链接保留原文件做种。

## 特性

- **监控**：watchdog 实时监听 + 文件稳定性检测（避免处理下载中的半成品）+ 定时兜底全量重扫
- **识别**：内置 [guessit](https://github.com/guessit-io/guessit) 解析标题/年份/季/集；可加 **TMDB 规则**把特定命名（番剧/字幕组）用正则直接钉到指定 `tmdb_id`，并可忽略某些季/集
- **刮削**：刮削器固定为 **TMDB**（电影/剧集元数据，置信度匹配 + 进程内缓存）——**需配置 API key**，缺失会直接报错而非乱整理
- **落地**：硬链接（跨盘自动回退复制）/ 复制（临时文件+原子改名）/ 移动；冲突可配 skip/overwrite/rename
- **命名 & 归类**：默认 Jellyfin 规范、模板可配；**动漫按 TMDB 题材（动画）自动归入 `Anime/`**
- **失败隔离**：转移/识别失败的文件移入 `failed_dir` 不再反复重试，可在 Web「文件」页**手动转移**（指定 TMDB ID）修复
- **状态**：SQLite 去重、记录映射、`undo` 回滚；记录可批量删除/改状态
- **可选**：生成 `.nfo` + 下载封面/fanart
- **插件化**：订阅器 / 下载器 / 通知器 / 媒体服务器可插拔（丢一个文件即生效）；刮削器(TMDB)、解析器(guessit) 为内置
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

**React SPA（Vite + TypeScript）** 前端 + FastAPI 提供 JSON API。仓库已含预构建产物，
运行无需 Node：

```bash
pip install -e '.[web]'              # 安装后端 Web 依赖(FastAPI/uvicorn)
mediamaid web -c config.yaml         # 浏览器打开 http://127.0.0.1:8500
```

提供：
- **仪表盘**：已整理/跳过/失败计数、最近记录，一键触发扫描（含 dry-run 预览）与订阅
- **文件**：浏览源目录/媒体库/失败目录；源目录视频文件显示**是否已转移**与识别信息，并可「识别」预览或「手动转移」（指定 TMDB ID / 类型 / 季集）落地
- **记录**：处理历史，可按状态过滤，支持**批量删除 / 批量改状态**
- **TMDB 规则**：正则绑定 `tmdb_id`（跳过搜索）+ 忽略指定季/集
- **订阅 / 下载**：订阅条目管理、资源预览/下载、下载任务监控
- **插件**：可启停的订阅器/下载器/通知器/媒体服务器（刮削器/解析器显示「内置」）
- **配置**：表单化编辑（路径、落地方式、失败目录、命名模板等），保存即热重载

可与 `mediamaid run` 守护进程同时运行（共享 SQLite，已开 WAL）。

### 前端开发

```bash
cd mediamaid/web/frontend
npm install
npm run dev          # 开发服务器，/api 代理到 127.0.0.1:8500（另开 mediamaid web）
npm run build        # 构建到 ../static/（提交进仓库供分发）
```

### 重启脚本

改了前端后需「重新构建 + 重启后端」才能在浏览器看到效果。`scripts/restart-web.sh`
把这套流程（构建前端 → 停旧进程 → 后台拉起 → 健康检查）封装成一条命令：

```bash
scripts/restart-web.sh                 # 构建前端并重启(默认)
scripts/restart-web.sh --no-build      # 跳过构建，仅重启后端
scripts/restart-web.sh --foreground    # 前台运行，便于看日志(Ctrl-C 退出)
```

可用环境变量覆盖默认值：`CONFIG`(默认 `demo/config.yaml`)、`HOST`(默认 `0.0.0.0`)、
`PORT`(默认 `8500`)、`PYTHON`(默认 `.venv/bin/python`)。后台模式日志默认写到
`/tmp/mediamaid_web.log`。

## 配置

见 `config.example.yaml`，含逐项注释。

## 插件系统

可插拔模块由 `config.yaml` 的 `plugins:` 段按名启用：

| 类别 | 接口方法 | 内置示例 |
|---|---|---|
| `subscriber` 订阅器 | `fetch() -> [Release]` | `rss` |
| `downloader` 下载器 | `add(release) -> bool` | `qbittorrent`, `transmission`, `aria2` |
| `notifier` 通知器 | `notify(event)` | `log`, `webhook` |
| `mediaserver` 媒体服务器 | `refresh()` | `emby` |

> **刮削器固定为 `tmdb`、解析器固定为 `guessit`（内置、始终启用、不可关闭）**，不在此列。
> RSS / qBittorrent 等需 `pip install 'mediamaid[plugins]'`。

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
docker compose up -d          # 本地构建并启动
```

**预构建镜像**：GitHub Actions（`.github/workflows/docker-publish.yml`）在打 `v*` tag
时自动构建多架构（amd64/arm64）镜像并发布到 GHCR（也可手动触发）。直接拉取：

```bash
docker pull ghcr.io/invokerw/mediamaid:latest
```

把 `docker-compose.yml` 里的 `build: .` 换成 `image: ghcr.io/invokerw/mediamaid:latest` 即可用预构建镜像。

### Docker 与目录（重要）

媒体工具最常见的坑就是目录/路径。遵循一条规则即可避免：

**① 同一挂载点**：把存放「下载」与「媒体库」的**同一个宿主目录**挂到容器（如 `/srv/media → /data`），让 `source_dirs`(下载) 和 `library_dir`(媒体库) 都在 `/data` 下。它们同属一个文件系统 → **硬链接生效**（否则跨设备会自动回退为复制，占双倍空间）。

```yaml
source_dirs: [/data/downloads]
library_dir: /data/media
```

**② 跨容器路径一致**：下载器（qBittorrent 等）通常是另一个容器。让它用**与 MediaMaid 完全相同**的宿主→容器映射（也挂 `/srv/media → /data`），下载保存到 `/data/downloads`。这样：
- 文件直接落进被监控的源目录 → watcher 自动整理；
- 下载器上报的路径 == MediaMaid 视角路径 → **无需任何转换**。

**③ 兜底：路径映射**：实在无法对齐（如沿用旧 qB 的 `/downloads`），给 qBittorrent 下载器配 `path_mappings`，把远端前缀翻译成本地前缀。**仅** `poll_completed`（轮询已完成任务）模式需要；watcher 模式只要文件落进源目录即可。

```yaml
plugins:
  downloader:
    - name: qbittorrent
      config:
        path_mappings: ["/downloads:/data/downloads"]   # 远端前缀:本地前缀
```

> Web「配置」页的目录字段可点「浏览」选择，无需手敲。

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
