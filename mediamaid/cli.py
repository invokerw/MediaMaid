"""命令行入口（typer）。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .config import load_config
from .logging_conf import setup_logging, get_logger
from .pipeline import Pipeline
from .store import StateStore
from .transfer import transfer as do_transfer
from .models import TransferAction
from .watcher import Watcher

app = typer.Typer(help="MediaMaid — 监控、识别、刮削并整理媒体到媒体库。", no_args_is_help=True)
console = Console()
log = get_logger("mediamaid")

DEFAULT_CONFIG = Path("config.yaml")


def _load(config: Path, verbose: bool):
    setup_logging(verbose)
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


def _print_results(results) -> None:
    by_status: dict = {}
    for r in results:
        by_status.setdefault(r.status, 0)
        by_status[r.status] += 1
    console.print(f"[bold]结果汇总:[/] {by_status}")


if __name__ == "__main__":
    app()
