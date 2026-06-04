"""串联四级流水线：识别 → 刮削 → 落地，并写状态库。"""

from __future__ import annotations

import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .config import Config
from .identify import Identifier
from .logging_conf import get_logger
from .models import Event, MediaInfo, MediaItem, MediaType, TransferAction
from .organizer import Organizer
from .plugins import MediaServer, Notifier, Scraper, close_plugins, create, load_plugins
from .store import StateStore

log = get_logger(__name__)


@dataclass
class Result:
    item: MediaItem
    status: str  # done / skipped / failed / unmatched
    dest: Optional[Path] = None
    error: Optional[str] = None


def build_scrapers(config: Config) -> List[Scraper]:
    """刮削器固定为 TMDB（始终启用、不可关闭）：取其配置实例化。
    未配置 api_key 直接报错——不再降级为仅按文件名整理。"""
    load_plugins()
    # 忽略 enabled 字段——刮削器不可关闭，仅取 tmdb 的配置块
    spec = next((s for s in config.plugins.get("scraper", []) if s.name == "tmdb"), None)
    tmdb_cfg = dict(spec.config) if spec else {}
    if not str(tmdb_cfg.get("api_key") or "").strip():
        raise RuntimeError(
            "未配置 TMDB API key：刮削器固定使用 TMDB，请在「插件」页或 config.yaml 的 "
            "plugins.scraper[tmdb].config.api_key 填写后再运行。"
        )
    return [create("scraper", "tmdb", tmdb_cfg)]


def build_notify(config: Config) -> Callable[[Event], None]:
    """构造一个独立的通知回调（只建通知器、不触碰刮削器），供订阅流程复用——
    订阅/通知本身无需 TMDB，借此避免缺 api_key 时被刮削器报错误伤。"""
    notifiers = build_notifiers(config)

    def _notify(event: Event) -> None:
        for n in notifiers:
            try:
                n.notify(event)
            except Exception as e:  # noqa: BLE001
                log.warning("通知器 %s 失败: %s", n.name, e)

    return _notify


def build_notifiers(config: Config) -> List[Notifier]:
    load_plugins()
    notifiers: List[Notifier] = []
    names = set()
    for spec in config.plugin_specs("notifier"):
        try:
            notifiers.append(create("notifier", spec.name, spec.config))
            names.add(spec.name)
        except Exception as e:  # noqa: BLE001
            log.error("加载通知器 %s 失败: %s", spec.name, e)
    # log 通知器内置常开（配置没显式启用也自动加上，保证「日志」页有内容）
    if "log" not in names:
        notifiers.insert(0, create("notifier", "log"))
    return notifiers


def build_mediaservers(config: Config) -> List[MediaServer]:
    load_plugins()
    servers: List[MediaServer] = []
    for spec in config.plugin_specs("mediaserver"):
        try:
            servers.append(create("mediaserver", spec.name, spec.config))
        except Exception as e:  # noqa: BLE001
            log.error("加载媒体服务器 %s 失败: %s", spec.name, e)
    return servers


class Pipeline:
    def __init__(self, config: Config, store: Optional[StateStore] = None):
        self.store = store
        # 按源文件粒度的串行锁：防止 watcher 与完成轮询两线程并发整理同一文件
        # （重复硬链接/重命名）。不同文件用不同锁，故不影响并行扫描。
        self._claim_locks: Dict[str, threading.Lock] = {}
        self._claim_guard = threading.Lock()
        self.reload(config)

    def _claim_lock(self, src: Path) -> threading.Lock:
        key = str(src)
        with self._claim_guard:
            lk = self._claim_locks.get(key)
            if lk is None:
                lk = threading.Lock()
                self._claim_locks[key] = lk
            return lk

    def reload(self, config: Config) -> None:
        """用新配置重建标识器/刮削器/通知器/整理器（热重载用，store 不变）。"""
        # 先关闭旧插件实例，避免 HTTP 连接/fd 泄漏
        close_plugins(getattr(self, "scrapers", None))
        close_plugins(getattr(self, "notifiers", None))
        close_plugins(getattr(self, "mediaservers", None))
        if getattr(self, "organizer", None) is not None:
            self.organizer.close()
        self.config = config
        self.identifier = Identifier(config)
        self.scrapers = build_scrapers(config)
        self.notifiers = build_notifiers(config)
        self.mediaservers = build_mediaservers(config)
        self.organizer = Organizer(config)

    def refresh_media_servers(self) -> None:
        """通知所有媒体服务器刷新库（异常不致命）。整理完一批后调用。"""
        for ms in self.mediaservers:
            try:
                ms.refresh()
            except Exception as e:  # noqa: BLE001
                log.warning("媒体服务器 %s 刷新失败: %s", ms.name, e)

    def _scrape(self, item: MediaItem) -> Optional[MediaInfo]:
        """链式刮削：依次尝试各刮削器，返回首个命中的结果。"""
        for scraper in self.scrapers:
            try:
                info = scraper.scrape(item)
            except Exception as e:  # noqa: BLE001
                log.warning("刮削器 %s 异常 %s: %s", scraper.name, item.source.name, e)
                continue
            if info is not None:
                return info
        return None

    # 公共别名：供 Web「识别」端点做只刮削不落地的预览
    def scrape(self, item: MediaItem) -> Optional[MediaInfo]:
        return self._scrape(item)

    def _move_to_failed(self, src: Path) -> Optional[Path]:
        """把转移失败的源文件移入失败目录隔离。未配置或移动失败返回 None。

        目标重名则追加 (1)、(2)… 避免覆盖；移动本身失败仅告警不抛。
        """
        if self.config.failed_dir is None:
            return None
        src = Path(src)
        if not src.exists():
            return None
        failed = Path(self.config.failed_dir)
        try:
            failed.mkdir(parents=True, exist_ok=True)
            dest = failed / src.name
            i = 1
            while dest.exists():
                dest = failed / f"{src.stem} ({i}){src.suffix}"
                i += 1
            shutil.move(str(src), str(dest))
            log.info("转移失败，已隔离到失败目录: %s -> %s", src.name, dest)
            return dest
        except OSError as e:
            log.error("移入失败目录失败 %s: %s", src, e)
            return None

    def _remove_target(self, dst: Path) -> None:
        """删除一个落地目标文件，并向上清理变空的父目录（到媒体库根为止）。"""
        try:
            if dst.exists() or dst.is_symlink():
                dst.unlink()
        except OSError as e:
            log.error("删除目标失败 %s: %s", dst, e)
            return
        lib = Path(self.config.library_dir).resolve()
        parent = dst.parent
        while True:
            rp = parent.resolve()
            if rp == lib or lib not in rp.parents:
                break
            try:
                parent.rmdir()  # 非空会抛 OSError
            except OSError:
                break
            parent = parent.parent

    def unorganize(self, src: Path) -> bool:
        """撤销某源文件的整理：删目标文件(+空目录) + 删 done 记录。

        move 动作无法恢复源文件，仅警告。返回是否删除了记录。
        """
        if not self.store:
            return False
        rec = self.store.done_record(src)
        if rec is None:
            return False
        if rec.dst_path:
            self._remove_target(Path(rec.dst_path))
            if rec.action == TransferAction.MOVE.value:
                log.warning("move 动作无法自动恢复源文件: %s", src)
        self.store.delete(rec.id)
        return True

    def organize_manual(self, item: MediaItem, info: MediaInfo) -> Result:
        """手动转移：强制按 info 落地；若该源此前已整理到别处，成功后再清理旧目标。

        安全顺序：先删旧 done 记录（让新 done 记录能写入），但**保留旧文件**；
        新转移成功且目标变化 → 删旧目标(+空目录)；新转移未成功(冲突/失败) →
        恢复旧记录，避免丢失对旧文件的跟踪、也不误删旧文件。
        """
        src = item.source
        old = self.store.done_record(src) if self.store else None
        old_dst = Path(old.dst_path) if (old and old.dst_path) else None
        if old and self.store:
            self.store.delete(old.id)
        result = self.process_item(item, force=True, override_info=info)
        if result.status == "done":
            if old_dst and result.dest and old_dst.resolve() != result.dest.resolve():
                self._remove_target(old_dst)
        elif old and self.store:
            # 新转移未发生：恢复旧记录（旧文件未动）
            self.store.record(
                src, str(old_dst) if old_dst else None, old.action, "done"
            )
        return result

    def notify(self, event: Event) -> None:
        for n in self.notifiers:
            try:
                n.notify(event)
            except Exception as e:  # noqa: BLE001
                log.warning("通知器 %s 失败: %s", n.name, e)

    def process_item(
        self,
        item: MediaItem,
        dry_run: bool = False,
        batch_id: Optional[str] = None,
        force: bool = False,
        override_info: Optional[MediaInfo] = None,
    ) -> Result:
        if item.media_type == MediaType.UNKNOWN:
            # 识别失败（类型未知）：配了失败目录则隔离，否则保持跳过
            if not dry_run and self.config.failed_dir is not None:
                moved = self._move_to_failed(item.source)
                if self.store:
                    self.store.record(item.source, moved, None, "failed", "未知媒体类型", batch_id)
                return Result(item, "failed", error="unknown type")
            log.warning("未知媒体类型，跳过: %s", item.source.name)
            return Result(item, "skipped", error="unknown type")

        # 非 dry-run 且有状态库时，对该源文件串行化：检查去重→落地→记录 一气呵成，
        # 避免并发线程对同一文件重复整理。force=True 时跳过去重（手动重处理）。
        if self.store and not dry_run:
            with self._claim_lock(item.source):
                return self._process_locked(item, batch_id, force, override_info)
        return self._process_unlocked(item, dry_run, batch_id, override_info)

    def _process_locked(
        self,
        item: MediaItem,
        batch_id: Optional[str],
        force: bool = False,
        override_info: Optional[MediaInfo] = None,
    ) -> Result:
        if not force and self.store.is_done(item.source):
            log.debug("已处理过，跳过: %s", item.source.name)
            return Result(item, "skipped", error="already done")
        return self._process_unlocked(item, False, batch_id, override_info)

    def _process_unlocked(
        self,
        item: MediaItem,
        dry_run: bool,
        batch_id: Optional[str],
        override_info: Optional[MediaInfo] = None,
    ) -> Result:
        # 刮削（失败不致命，降级为仅文件名）；override_info 非空时直接用它（手动转移）
        info = override_info if override_info is not None else self._scrape(item)

        # TMDB 规则忽略：已知 tmdb_id（绑定或自动匹配）的某些季/集不整理
        tmdb_id = info.tmdb_id if info else item.tmdb_id
        if tmdb_id and self.config.is_ignored(tmdb_id, item.season, item.episode):
            log.info("被 TMDB 规则忽略，跳过: %s", item.source.name)
            return Result(item, "skipped", error="被 TMDB 规则忽略")

        try:
            plan = self.organizer.plan(item, info)
            dest = self.organizer.execute(plan, dry_run=dry_run)
        except Exception as e:  # noqa: BLE001
            log.error("落地失败 %s: %s", item.source.name, e)
            # 转移失败：把源文件移入失败目录隔离（不再自动重试），记录其去向
            moved = None if dry_run else self._move_to_failed(item.source)
            if self.store and not dry_run:
                self.store.record(
                    item.source, moved, self.config.action.value, "failed", str(e), batch_id
                )
            if not dry_run:
                self.notify(Event("error", f"落地失败: {item.source.name}: {e}", item=item))
            return Result(item, "failed", error=str(e))

        if dest is None:
            return Result(item, "skipped", error="conflict skip")

        if self.store and not dry_run:
            self.store.record(item.source, dest, plan.action.value, "done", batch_id=batch_id)
        if not dry_run:
            self.notify(Event("organized", f"已整理: {dest.name}", item=item, info=info, dest=dest))
        return Result(item, "done", dest=dest)

    def _handle_unidentified(
        self, path: Path, dry_run: bool, batch_id: Optional[str]
    ) -> Optional[Result]:
        """识别失败（解析不出标题）的候选文件：配了失败目录则隔离 + 记录，否则跳过。"""
        if dry_run or self.config.failed_dir is None:
            return None
        moved = self._move_to_failed(path)
        if self.store:
            self.store.record(path, moved, None, "failed", "无法识别", batch_id)
        self.notify(Event("error", f"无法识别，已隔离: {path.name}"))
        placeholder = MediaItem(source=path, media_type=MediaType.UNKNOWN, title=path.stem)
        return Result(placeholder, "failed", error="无法识别")

    def _route_path(
        self, path: Path, dry_run: bool, batch_id: Optional[str]
    ) -> Optional[Result]:
        """对一个候选文件：识别成功 → 整理；识别失败 → 隔离（见 _handle_unidentified）。"""
        item = self.identifier.identify(path)
        if item is None:
            return self._handle_unidentified(path, dry_run, batch_id)
        return self.process_item(item, dry_run=dry_run, batch_id=batch_id)

    def process_path(
        self, path: Path, dry_run: bool = False, batch_id: Optional[str] = None
    ) -> Optional[Result]:
        """处理单个文件路径（供 watcher 调用）。"""
        path = Path(path)
        if not self.identifier.accept_file(path) or self.config.under_failed(path):
            return None
        if batch_id is None and self.store and not dry_run:
            batch_id = self.store.new_batch_id()
        return self._route_path(path, dry_run, batch_id)

    def process_target(self, path: Path, dry_run: bool = False) -> List[Result]:
        """处理一个文件或目录目标（供下载完成轮询用）。

        目录（多文件种子）→ 扫描其中候选文件逐个处理；文件 → 单个处理。
        同一目标内的多文件共享一个 batch_id，便于按批 undo。
        """
        path = Path(path)
        batch_id = self.store.new_batch_id() if (self.store and not dry_run) else None
        if path.is_dir():
            results = [
                self._route_path(p, dry_run, batch_id)
                for p in self.identifier.accepted_paths([path])
            ]
            results = [r for r in results if r is not None]
        else:
            result = self.process_path(path, dry_run=dry_run, batch_id=batch_id)
            results = [result] if result is not None else []
        if not dry_run and any(r and r.status == "done" for r in results):
            self.refresh_media_servers()
        return results

    def scan(self, dry_run: bool = False) -> List[Result]:
        """全量扫描所有源目录并处理。

        scan_workers>1 时用有界线程池并行（瓶颈是 TMDB 网络请求）；
        process_item 本身线程安全（按源文件串行 + thread-local DB 连接）。
        """
        paths = self.identifier.accepted_paths(self.config.source_dirs)
        log.info("发现 %d 个候选文件", len(paths))
        batch_id = self.store.new_batch_id() if (self.store and not dry_run) else None

        workers = max(1, self.config.scan_workers)
        if workers == 1 or len(paths) <= 1:
            results = [self._route_path(p, dry_run, batch_id) for p in paths]
        else:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=min(workers, len(paths))) as pool:
                results = list(
                    pool.map(lambda p: self._route_path(p, dry_run, batch_id), paths)
                )
        # 识别失败且未配失败目录时 _route_path 返回 None，过滤掉
        results = [r for r in results if r is not None]
        done = sum(1 for r in results if r.status == "done")
        log.info("完成: %d done / %d 总数", done, len(results))
        if not dry_run and done:
            self.refresh_media_servers()
        return results
