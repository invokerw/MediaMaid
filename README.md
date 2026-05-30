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
mediamaid watch                      # 常驻监控
mediamaid status                     # 查看最近处理记录
mediamaid undo                       # 回滚最近一批
mediamaid identify <文件路径>         # 调试单个文件的识别结果
```

## 配置

见 `config.example.yaml`，含逐项注释。

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
SourceWatcher ─► Identifier ─► Scraper ─► Organizer
   watcher.py    identify.py   scraper/   organizer.py + transfer.py + naming.py
        \____________ StateStore(store.py) / Config(config.py) ____________/
                          Pipeline(pipeline.py) 串联
```
