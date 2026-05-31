import time
from pathlib import Path

import yaml

from mediamaid.config import ConfigManager


def _write(path: Path, **extra):
    data = {
        "source_dirs": [str(path.parent / "dl")],
        "library_dir": str(path.parent / "lib"),
        "state_db": str(path.parent / "s.db"),
        **extra,
    }
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def test_manager_auto_reloads_on_change(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    _write(cfg_path, stable_seconds=10)

    mgr = ConfigManager(cfg_path)
    assert mgr.get().stable_seconds == 10

    # 修改文件（确保 mtime/size 变化）
    time.sleep(0.01)
    _write(cfg_path, stable_seconds=99, rescan_interval=123)

    cfg = mgr.get()
    assert cfg.stable_seconds == 99
    assert cfg.rescan_interval == 123


def test_pipeline_reload_rebuilds(tmp_path):
    from mediamaid.config import load_config
    from mediamaid.pipeline import Pipeline

    cfg_path = tmp_path / "config.yaml"
    _write(cfg_path, plugins={"notifier": [{"name": "log"}]})
    pipe = Pipeline(load_config(cfg_path))
    assert [n.name for n in pipe.notifiers] == ["log"]

    _write(cfg_path, plugins={})
    pipe.reload(load_config(cfg_path))
    assert pipe.notifiers == []
