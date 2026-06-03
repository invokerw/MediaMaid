# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

MediaMaid 是一个媒体整理自动化工具：**监控源目录 → 解析/识别 → 刮削元数据 → 复制/硬链接/移动到媒体库**，并可串联订阅与下载形成闭环。代码内注释与文档以中文为主，保持一致。

## 常用命令

```bash
# 安装（开发用，含可选依赖组）
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev,plugins,web]"

# 测试
.venv/bin/pytest                     # 全量
.venv/bin/pytest tests/test_pipeline.py            # 单文件
.venv/bin/pytest tests/test_pipeline.py::test_xxx  # 单用例
.venv/bin/pytest -k store -q                       # 按名筛选

# 运行 CLI（入口 mediamaid = mediamaid.cli:app）
.venv/bin/mediamaid scan --dry-run -c config.yaml  # 预览整理计划
.venv/bin/mediamaid scan -c config.yaml            # 执行一次整理
.venv/bin/mediamaid watch -c config.yaml           # 常驻监控
.venv/bin/mediamaid run -c config.yaml             # 全自动闭环守护
.venv/bin/mediamaid identify <文件>                 # 调试单文件识别结果
.venv/bin/mediamaid plugins                        # 列出已发现插件

# Web 界面（端口默认 8500）
.venv/bin/mediamaid web -c config.yaml

# 改了前端后：重新构建 + 重启后端（见 scripts/restart-web.sh）
scripts/restart-web.sh                 # 构建前端 → 停旧进程 → 后台拉起 → 健康检查
scripts/restart-web.sh --no-build      # 仅重启后端
```

无 lint/format 工具配置；测试仅依赖 `pytest`（无额外 markers/addopts）。本仓库默认用 `demo/config.yaml` 跑本地 Web（端口 8500）。

## 架构大图

数据沿一条流水线流动，四级阶段各由一类可插拔插件承担：

```
订阅器 fetch ─► 去重 ─► 下载器 add ─► (下载到 source_dirs)
                                          │
源目录监控(watcher) ◄──────────────────────┘
   │ 文件稳定后
   └─► 解析/识别(identify) ─► 刮削(scraper) ─► 整理入库(organizer) ─► 通知器 / 媒体服务器刷新
```

- **`pipeline.py` 是核心编排器**。`Pipeline.process_item/process_path/process_target/scan` 串起识别→刮削→落地→写状态库。`build_notifiers/build_mediaservers` 按配置实例化插件。**刮削器固定为 TMDB（始终启用、不可关闭，不再支持其他刮削器）**：`build_scrapers` 只实例化 tmdb，**未配置 api_key 直接抛 `RuntimeError`**（不再降级为仅按文件名整理）。订阅/通知流程不需要刮削器，用 `build_notify(config)` 单独构造通知回调，避免缺 key 时被误伤。
- **`daemon.py`（`mediamaid run`）** 把 watcher + 订阅轮询 + 完成轮询 + 配置热重载合成一个常驻进程，每条都是 daemon 线程。是理解“闭环”的入口。
- **`identify.py`** 用**解析器链**（`config.parsers` 顺序）把文件名解析成 `MediaItem`；`guessit` 始终作为最后兜底（用户没显式配它就自动追加）。
- **`organizer.py` + `naming.py` + `transfer.py`**：`organizer.plan()` 算目标路径（命名模板见 `config.NamingConfig`），`transfer` 执行硬链接（跨盘自动回退复制）/复制（临时文件+原子改名）/移动，冲突按 `on_conflict`（skip/overwrite/rename）处理。

## 插件系统（核心扩展点）

六个类别，基类在 `mediamaid/plugins/base.py`：`parser` / `scraper` / `subscriber` / `downloader` / `notifier` / `mediaserver`。

- **新增插件 = 在 `mediamaid/plugins/<category>/` 放一个 `.py`，继承对应基类并 `@register`**（`plugins/registry.py`）。文件落地即被自动发现（目录扫描），无需改注册表。
- 插件声明类属性 `category` / `name`，并可声明 `ConfigModel`（pydantic）做配置校验。`create(category, name, config)` 会用 `ConfigModel.model_validate` 校验后实例化。
- **重依赖务必在 `__init__`/方法内惰性 import**，否则缺该依赖会让 `load_plugins()` 整体受影响（registry 对单模块加载失败是容错的，但惰性 import 是约定）。
- **可选依赖统一用 `plugins/deps.py` 的 `require(module, pip_name)` 惰性加载**：缺失时自动 `pip install` 后重试，返回 `(模块, 错误信息)`。约定——`_conn()` 等用它拿模块，把返回的错误信息存到 `self._conn_error`，`test()` 据此回显（缺依赖/安装失败 vs 登录/连接失败要分开报，别收敛成一句笼统提示）。自动安装默认开启，`MEDIAMAID_AUTO_INSTALL=0` 可关闭（离线环境）。参考 `downloader/qbittorrent.py`。
- 外部 pip 包可经 entry_points 组 `mediamaid.plugins` 提供插件（见 `pyproject.toml` 注释）。
- `load_plugins()` 幂等；持有连接的插件应覆写 `close()`，热重载替换实例前会调用以避免 fd/连接泄漏。

可选依赖分组（`pyproject.toml`）：`plugins`（feedparser/qbittorrent-api/transmission-rpc）、`web`（fastapi/uvicorn/ruamel.yaml）、`dev`（pytest）。

## 配置与热重载

- `config.py` 用 pydantic 校验 YAML（见 `config.example.yaml` 逐项注释）。`Config.plugin_specs(category)` 取某类别启用的插件实例；`subscriptions` 与 `parsers` 是命名实例列表（区别于 `plugins.subscriber`）。
- **`ConfigManager` 按文件 mtime+size 自动热重载**，线程安全。Web 与守护进程都通过它读配置：任一方写盘后，其他读取方下次 `get()` 自动感知。`daemon` 的配置监视线程检测到变更会调各组件的 `reload()` 热重建。修改配置流程时，注意 reload 路径要把旧插件 `close()` 掉。

## 状态库并发模型（store.py）

SQLite，**每线程一个连接（thread-local）+ WAL + busy_timeout**——读不互相阻塞、写由 SQLite 自身串行化，进程内无全局锁。`processed` 表去重并支持 `undo`（按 `batch_id` 成批回滚）；`seen_releases` 给订阅去重。`scan` 用 `scan_workers` 个线程并行（瓶颈是 TMDB 网络），`Pipeline` 用按源文件粒度的锁串行化“查重→落地→记录”避免重复整理同一文件。可与 `mediamaid run` 同时运行（共享同一 DB）。

## Web 前端

后端 FastAPI（`mediamaid/web/`）：`app.py` 装配应用并挂载 `routers/` 下各领域 router（API 全在 `/api/*`），catch-all 托管 React SPA。`deps.py` 的 `WebContext`（挂 `app.state.ctx`）提供配置/状态库/`safe_path`（路径安全：只允许操作 source_dirs/library_dir 范围内）。

前端是 **Vite + React + TypeScript + Ant Design**（`mediamaid/web/frontend/`），构建产物输出到 `mediamaid/web/static/`（提交进仓库，运行无需 Node）。

```bash
cd mediamaid/web/frontend
npm install
npm run dev          # 开发服务器，/api 代理到 127.0.0.1:8500
npm run build        # 构建到 ../static/，并提交
```

**关键：改了前端 `.tsx` 源码后，浏览器看不到变化，必须 `npm run build`（或 `scripts/restart-web.sh`）重建静态产物并重启后端。**
