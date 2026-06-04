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


def _load(path: Path):
    yaml = _yaml()
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return yaml, (yaml.load(f) or {})
    return yaml, {}


def add_list_item(path: Path, key: str, item: dict) -> None:
    """向顶层 key 的列表追加一项（保留注释）。"""
    path = Path(path)
    yaml, data = _load(path)
    lst = data.get(key)
    if lst is None:
        lst = []
        data[key] = lst
    lst.append(item)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f)


def update_list_item(path: Path, key: str, item_id: str, fields: dict) -> bool:
    """按 id 更新顶层 key 列表中的一项；返回是否命中。"""
    path = Path(path)
    yaml, data = _load(path)
    for s in data.get(key, []):
        if s.get("id") == item_id:
            for k, v in fields.items():
                s[k] = v
            with path.open("w", encoding="utf-8") as f:
                yaml.dump(data, f)
            return True
    return False


def delete_list_item(path: Path, key: str, item_id: str) -> bool:
    path = Path(path)
    yaml, data = _load(path)
    lst = data.get(key, [])
    new = [s for s in lst if s.get("id") != item_id]
    if len(new) == len(lst):
        return False
    data[key] = new
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f)
    return True


# 订阅 CRUD（向后兼容包装）
def add_subscription(path: Path, sub: dict) -> None:
    add_list_item(path, "subscriptions", sub)


def update_subscription(path: Path, sub_id: str, fields: dict) -> bool:
    return update_list_item(path, "subscriptions", sub_id, fields)


def delete_subscription(path: Path, sub_id: str) -> bool:
    return delete_list_item(path, "subscriptions", sub_id)


# 嵌套对象类键，做 mapping 级合并而非整体替换
_NESTED_KEYS = {"filters", "naming", "auth"}


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
