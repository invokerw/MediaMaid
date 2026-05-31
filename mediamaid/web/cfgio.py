"""配置文件写回：保留注释/格式地编辑 config.yaml 的 plugins 段。

读取仍由 config.load_config（PyYAML）负责；这里只在 Web 写配置时用 ruamel.yaml
做读-改-写往返，避免丢失用户配置里的注释。
"""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def upsert_plugin(
    path: Path,
    category: str,
    name: str,
    enabled: bool,
    config: dict,
) -> None:
    """在 config.yaml 的 plugins[category] 列表中按 name 插入/更新一条插件配置。"""
    path = Path(path)
    yaml = _yaml()

    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            data = yaml.load(f) or {}
    else:
        data = {}

    plugins = data.setdefault("plugins", {})
    specs = plugins.get(category)
    if specs is None:
        specs = []
        plugins[category] = specs

    spec = None
    for s in specs:
        if s.get("name") == name:
            spec = s
            break
    if spec is None:
        spec = {"name": name}
        specs.append(spec)

    spec["enabled"] = enabled
    if config:
        spec["config"] = config
    elif "config" in spec:
        # 无参插件：清掉空 config 键保持整洁
        del spec["config"]

    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f)
