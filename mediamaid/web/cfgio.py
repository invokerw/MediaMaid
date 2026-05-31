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


# 嵌套对象类键，做 mapping 级合并而非整体替换
_NESTED_KEYS = {"filters", "naming"}


def update_settings(path: Path, values: dict) -> None:
    """更新 config.yaml 的顶层设置（保留注释）。

    values 中 filters/naming 做子键合并，其余顶层键直接赋值；值为 None 的键忽略。
    """
    path = Path(path)
    yaml = _yaml()
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            data = yaml.load(f) or {}
    else:
        data = {}

    for key, val in values.items():
        if val is None:
            continue
        if key in _NESTED_KEYS and isinstance(val, dict):
            sub = data.get(key)
            if not isinstance(sub, dict):
                sub = {}
                data[key] = sub
            for k, v in val.items():
                if v is not None:
                    sub[k] = v
        else:
            data[key] = val

    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f)
