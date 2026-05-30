"""命令行入口（typer）。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .config import load_config
from .daemon import Daemon
from .logging_conf import setup_logging, get_logger
from .pipeline import Pipeline
from .plugins import CATEGORIES, available, load_plugins
from .store import StateStore
from .models import TransferAction
from .subscribe import SubscribeRunner
from .watcher import Watcher

app = typer.Typer(help="MediaMaid — 监控、识别、刮削并整理媒体到媒体库。", no_args_is_help=True)
console = Console()
log = get_logger("mediamaid")

DEFAULT_CONFIG = Path("config.yaml")


def _load(config: Path, verbose: bool):
    setup_logging(verbose)
    load_plugins()
    return load_config(config)


@app.command()
def scan(
    config: Path = typer.Option(DEFAULT_CONFIG, "--config", "-c", help="配置文件路径"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="只打印计划不落地"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """对源目录做一次全量扫描整理。"""
    cfg = _load(config, verbose)
    with StateStore(cfg.state_db) as store:
        pipeline = Pipeline(cfg, store)
        results = pipeline.scan(dry_run=dry_run)
    _print_results(results)


@app.command()
def watch(
    config: Path = typer.Option(DEFAULT_CONFIG, "--config", "-c"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """常驻监控源目录，自动整理新文件。"""
    cfg = _load(config, verbose)
    with StateStore(cfg.state_db) as store:
        pipeline = Pipeline(cfg, store)
        Watcher(cfg, pipeline).start()


@app.command()
def run(
    config: Path = typer.Option(DEFAULT_CONFIG, "--config", "-c"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """全自动闭环守护：订阅→下载→监控→识别/刮削/整理→通知，一条龙常驻。"""
    cfg = _load(config, verbose)
    with StateStore(cfg.state_db) as store:
        Daemon(cfg, store).run()


@app.command()
def web(
    config: Path = typer.Option(DEFAULT_CONFIG, "--config", "-c"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8500, "--port"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """启动 Web 管理界面（需 pip install 'mediamaid[web]'）。"""
    setup_logging(verbose)
    try:
        import uvicorn

        from .web import create_app
    except ImportError:
        console.print("[red]缺少 Web 依赖，请先安装：pip install 'mediamaid[web]'[/]")
        raise typer.Exit(1)
    application = create_app(config)
    console.print(f"[green]MediaMaid Web 启动:[/] http://{host}:{port}")
    uvicorn.run(application, host=host, port=port)


@app.command()
def status(
    config: Path = typer.Option(DEFAULT_CONFIG, "--config", "-c"),
    limit: int = typer.Option(30, "--limit", "-l"),
):
    """查看最近处理记录。"""
    cfg = _load(config, False)
    with StateStore(cfg.state_db) as store:
        records = store.recent(limit)
    table = Table(title="最近处理记录")
    table.add_column("ID", justify="right")
    table.add_column("状态")
    table.add_column("动作")
    table.add_column("源文件")
    table.add_column("目标")
    for r in records:
        table.add_row(
            str(r.id), r.status, r.action or "-",
            Path(r.src_path).name,
            Path(r.dst_path).name if r.dst_path else "-",
        )
    console.print(table)


@app.command()
def undo(
    config: Path = typer.Option(DEFAULT_CONFIG, "--config", "-c"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
):
    """回滚最近一批整理（删除媒体库中生成的文件/链接）。"""
    cfg = _load(config, False)
    with StateStore(cfg.state_db) as store:
        batch = store.last_batch_done()
        if not batch:
            console.print("[yellow]没有可回滚的记录[/]")
            raise typer.Exit()
        console.print(f"将回滚 [bold]{len(batch)}[/] 条记录：")
        for r in batch:
            console.print(f"  - {r.dst_path}")
        if not yes and not typer.confirm("确认删除以上目标文件？"):
            raise typer.Exit()
        for r in batch:
            if r.dst_path:
                p = Path(r.dst_path)
                try:
                    if p.exists():
                        p.unlink()
                    # move 动作无法还原源文件，提示
                    if r.action == TransferAction.MOVE.value:
                        log.warning("move 动作无法自动恢复源文件: %s", r.src_path)
                except OSError as e:
                    log.error("删除失败 %s: %s", p, e)
            store.delete(r.id)
    console.print("[green]回滚完成[/]")


@app.command()
def identify(
    path: Path = typer.Argument(..., help="要解析的文件路径"),
    config: Path = typer.Option(DEFAULT_CONFIG, "--config", "-c"),
):
    """调试：打印某文件的识别结果与目标路径。"""
    cfg = _load(config, True)
    pipeline = Pipeline(cfg)
    item = pipeline.identifier.identify(path)
    if item is None:
        console.print("[red]无法识别[/]")
        raise typer.Exit(1)
    console.print(item)
    plan = pipeline.organizer.plan(item, None)
    console.print(f"目标(仅文件名规则): {plan.dest}")


@app.command()
def subscribe(
    config: Path = typer.Option(DEFAULT_CONFIG, "--config", "-c"),
    loop: bool = typer.Option(False, "--loop", help="周期循环运行而非跑一次"),
    interval: int = typer.Option(600, "--interval", help="--loop 时每轮间隔秒数"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """运行订阅器发现新资源并交给下载器。"""
    cfg = _load(config, verbose)
    with StateStore(cfg.state_db) as store:
        pipeline = Pipeline(cfg, store)
        runner = SubscribeRunner(cfg, store, notify=pipeline.notify)
        if loop:
            runner.run_loop(interval)
        else:
            runner.run_once()


@app.command()
def plugins(verbose: bool = typer.Option(False, "--verbose", "-v")):
    """列出已发现的全部插件。"""
    setup_logging(verbose)
    load_plugins()
    table = Table(title="已注册插件")
    table.add_column("类别")
    table.add_column("插件名")
    for category in CATEGORIES:
        names = available(category)
        table.add_row(category, ", ".join(names) if names else "[dim](无)[/]")
    console.print(table)


def _print_results(results) -> None:
    by_status: dict = {}
    for r in results:
        by_status.setdefault(r.status, 0)
        by_status[r.status] += 1
    console.print(f"[bold]结果汇总:[/] {by_status}")


if __name__ == "__main__":
    app()
