from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from mediamaid.web import create_app

BIG = b"0" * (60 * 1024 * 1024)


def _authed(app, username="admin", password="admin"):
    """建 TestClient 并登录，默认带上 Bearer token。"""
    c = TestClient(app)
    tok = c.post("/api/login", json={"username": username, "password": password}).json()["token"]
    c.headers.update({"Authorization": f"Bearer {tok}"})
    return c


@pytest.fixture
def client(tmp_path):
    src = tmp_path / "downloads"
    src.mkdir()
    (src / "The.Matrix.1999.1080p.mkv").write_bytes(BIG)
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump(
            {
                "source_dirs": [str(src)],
                "library_dir": str(tmp_path / "media"),
                "state_db": str(tmp_path / "s.db"),
                "plugins": {},
            }
        ),
        encoding="utf-8",
    )
    return _authed(create_app(cfg_path)), tmp_path


def test_dashboard_api(client):
    c, _ = client
    r = c.get("/api/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert "counts" in body and "records" in body


def test_auth_required_and_login(client):
    c, _ = client
    # 无 token → 401
    noauth = TestClient(c.app)
    assert noauth.get("/api/dashboard").status_code == 401
    # 错密码 → 401
    assert noauth.post("/api/login", json={"username": "admin", "password": "x"}).status_code == 401
    # 正确登录 → 拿 token 后可访问
    tok = noauth.post("/api/login", json={"username": "admin", "password": "admin"}).json()["token"]
    noauth.headers.update({"Authorization": f"Bearer {tok}"})
    assert noauth.get("/api/dashboard").status_code == 200
    assert noauth.get("/api/me").json()["username"] == "admin"


def test_env_credentials_override(client, monkeypatch):
    c, _ = client
    monkeypatch.setenv("MEDIAMAID_USERNAME", "boss")
    monkeypatch.setenv("MEDIAMAID_PASSWORD", "s3cret")
    fresh = TestClient(c.app)
    # 默认 admin/admin 失效，环境变量账号生效
    assert fresh.post("/api/login", json={"username": "admin", "password": "admin"}).status_code == 401
    r = fresh.post("/api/login", json={"username": "boss", "password": "s3cret"})
    assert r.status_code == 200
    tok = r.json()["token"]
    fresh.headers.update({"Authorization": f"Bearer {tok}"})
    me = fresh.get("/api/me").json()
    assert me["username"] == "boss" and me["env_managed"] is True
    # 环境变量接管时禁止改账号
    assert fresh.put("/api/account", json={"current_password": "s3cret", "password": "x"}).status_code == 400


def test_change_account(client):
    c, _ = client
    # 当前密码错 → 403
    assert c.put("/api/account", json={"current_password": "wrong", "password": "newpass"}).status_code == 403
    # 改密码
    assert c.put("/api/account", json={"current_password": "admin", "password": "newpass"}).status_code == 200
    fresh = TestClient(c.app)
    # 旧密码失效、新密码可登录
    assert fresh.post("/api/login", json={"username": "admin", "password": "admin"}).status_code == 401
    assert fresh.post("/api/login", json={"username": "admin", "password": "newpass"}).status_code == 200


def test_logs_endpoint(client):
    c, _ = client
    r = c.get("/api/logs")
    assert r.status_code == 200 and "logs" in r.json()


def test_log_notifier_is_builtin(client):
    c, _ = client
    cats = {cat["category"]: cat for cat in c.get("/api/plugins").json()["categories"]}
    log = next(e for e in cats["notifier"]["entries"] if e["name"] == "log")
    assert log["builtin"] is True and log["enabled"] is True
    # 请求停用也强制保持启用
    r = c.put("/api/plugins/notifier/log", json={"enabled": False, "config": {}})
    assert r.status_code == 200 and r.json()["enabled"] is True


def test_plugins_api_lists_builtins(client):
    c, _ = client
    r = c.get("/api/plugins")
    assert r.status_code == 200
    names = {
        e["name"]
        for cat in r.json()["categories"]
        for e in cat["entries"]
    }
    assert "tmdb" in names
    assert "log" in names


def test_files_meta_enrichment(client):
    c, tmp_path = client
    src = str((tmp_path / "downloads"))
    r = c.get(f"/api/files?path={src}&meta=1")
    assert r.status_code == 200
    e = next(x for x in r.json()["entries"] if x["name"].endswith(".mkv"))
    assert e["is_video"] is True
    assert e["organized"] is False
    assert e["parsed"]["title"] == "The Matrix"
    assert e["parsed"]["year"] == 1999
    assert e["parsed"]["media_type"] == "movie"


def test_organize_identify_without_key(client):
    c, tmp_path = client
    path = str(tmp_path / "downloads" / "The.Matrix.1999.1080p.mkv")
    r = c.post("/api/organize/identify", json={"path": path})
    assert r.status_code == 200
    body = r.json()
    # 无 TMDB key：仅解析，matched 为空
    assert body["has_key"] is False
    assert body["matched"] is None
    assert body["parsed"]["title"] == "The Matrix"


def test_failed_dir_root_and_manual_scope(tmp_path):
    # 配了 failed_dir 的独立 app
    src = tmp_path / "downloads"
    src.mkdir()
    failed = tmp_path / "failed"
    failed.mkdir()
    (failed / "Boom.2020.1080p.mkv").write_bytes(BIG)
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump({
            "source_dirs": [str(src)],
            "library_dir": str(tmp_path / "media"),
            "failed_dir": str(failed),
            "state_db": str(tmp_path / "s.db"),
            "plugins": {},
        }),
        encoding="utf-8",
    )
    c = _authed(create_app(cfg_path))

    # 根选择器含「失败: …」
    roots = c.get("/api/files/roots").json()["roots"]
    assert any(r["label"].startswith("失败") for r in roots)

    # 失败目录中的文件可识别（_source_path 放行），无 key 仅解析
    r = c.post("/api/organize/identify",
               json={"path": str(failed / "Boom.2020.1080p.mkv")})
    assert r.status_code == 200 and r.json()["parsed"]["title"] == "Boom"

    # 媒体库内文件仍被拒
    r2 = c.post("/api/organize/identify", json={"path": str(tmp_path / "media" / "x.mkv")})
    assert r2.status_code in (400, 404)


def test_organize_manual_rejects_library_path(client):
    c, tmp_path = client
    lib_file = str(tmp_path / "media" / "x.mkv")  # 媒体库内 → 拒绝
    r = c.post(
        "/api/organize/manual",
        json={"path": lib_file, "tmdb_id": 1, "media_type": "movie"},
    )
    assert r.status_code in (400, 404)


def test_config_api(client):
    c, _ = client
    r = c.get("/api/config")
    assert r.status_code == 200
    assert "library_dir" in r.json()["text"]


def test_scan_dry_run_then_real(client):
    c, tmp_path = client
    media = tmp_path / "media"

    r = c.post("/api/scan", json={"dry_run": True})
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True
    assert body["summary"].get("done") == 1
    assert not media.exists()

    r = c.post("/api/scan", json={"dry_run": False})
    assert r.json()["summary"].get("done") == 1
    assert (media / "Movies" / "The Matrix (1999)" / "The Matrix (1999).mkv").exists()

    r = c.get("/api/records")
    names = {rec["dst_name"] for rec in r.json()["records"]}
    assert "The Matrix (1999).mkv" in names


def test_spa_served_at_root(client):
    c, _ = client
    # 已构建：返回 index.html（含 root 挂载点）；未构建：503 提示
    r = c.get("/")
    assert r.status_code in (200, 503)
    if r.status_code == 200:
        assert 'id="root"' in r.text
    # 未知前端路由也应回退到 SPA（非 /api）
    r2 = c.get("/records")
    assert r2.status_code in (200, 503)


def test_unknown_api_404(client):
    c, _ = client
    assert c.get("/api/nope").status_code == 404


def test_fs_list(client, tmp_path):
    c, _ = client
    base = tmp_path / "browse"
    base.mkdir()
    (base / "subA").mkdir()
    (base / "subB").mkdir()
    (base / "file.txt").write_text("x", encoding="utf-8")
    r = c.get("/api/fs", params={"path": str(base)})
    assert r.status_code == 200
    body = r.json()
    names = {d["name"] for d in body["dirs"]}
    assert names == {"subA", "subB"}  # 只列目录，不含 file.txt
    assert body["error"] is None


def test_fs_list_bad_path(client):
    c, _ = client
    r = c.get("/api/fs", params={"path": "/no/such/dir/xyz"})
    assert r.status_code == 200
    assert r.json()["error"]


def test_files_roots_and_list(client, tmp_path):
    c, _ = client
    src = tmp_path / "downloads"
    (src / "a.mkv").write_bytes(b"x")
    (src / "sub").mkdir()

    roots = c.get("/api/files/roots").json()["roots"]
    assert any("源目录" in r["label"] for r in roots)
    assert any("媒体库" in r["label"] for r in roots)

    entries = c.get("/api/files", params={"path": str(src)}).json()["entries"]
    by_name = {e["name"]: e for e in entries}
    assert by_name["a.mkv"]["is_dir"] is False
    assert by_name["sub"]["is_dir"] is True


def test_files_rename_and_delete(client, tmp_path):
    c, _ = client
    src = tmp_path / "downloads"
    f = src / "old.mkv"
    f.write_bytes(b"x")

    # 重命名
    r = c.post("/api/files/rename", json={"path": str(f), "name": "new.mkv"})
    assert r.status_code == 200
    assert (src / "new.mkv").exists() and not f.exists()

    # 删除文件
    assert c.post("/api/files/delete", json={"path": str(src / "new.mkv")}).status_code == 200
    assert not (src / "new.mkv").exists()

    # 删除目录(递归)
    d = src / "folder"
    (d / "inner.mkv").parent.mkdir()
    (d / "inner.mkv").write_bytes(b"x")
    assert c.post("/api/files/delete", json={"path": str(d)}).status_code == 200
    assert not d.exists()


def test_files_security(client, tmp_path):
    c, _ = client
    src = tmp_path / "downloads"
    # 越界路径 → 403
    assert c.get("/api/files", params={"path": "/etc"}).status_code == 403
    assert c.post("/api/files/delete", json={"path": "/etc/hosts"}).status_code == 403
    # 删受管根本身 → 403
    assert c.post("/api/files/delete", json={"path": str(src)}).status_code == 403
    # 非法新名 → 400
    f = src / "x.mkv"
    f.write_bytes(b"x")
    assert c.post(
        "/api/files/rename", json={"path": str(f), "name": "../escape"}
    ).status_code == 400


def test_diag_hardlink(client):
    c, tmp_path = client
    # client fixture 的 source_dir 与 library 同在 tmp_path 下 → 同一文件系统
    r = c.get("/api/diag/hardlink")
    assert r.status_code == 200
    body = r.json()
    assert body["results"], "应有至少一个源目录结果"
    assert all(x["ok"] for x in body["results"])


def test_plugins_expose_schema(client):
    c, _ = client
    r = c.get("/api/plugins")
    cats = {cat["category"]: cat for cat in r.json()["categories"]}
    tmdb = next(e for e in cats["scraper"]["entries"] if e["name"] == "tmdb")
    assert "api_key" in tmdb["schema"]["properties"]
    log = next(e for e in cats["notifier"]["entries"] if e["name"] == "log")
    assert log["schema"]["properties"] == {} or "properties" not in log["schema"] \
        or log["schema"].get("properties") == {}


def test_plugin_update_persists_and_reloads(client):
    from mediamaid.config import load_config

    c, tmp_path = client
    cfg_path = tmp_path / "config.yaml"

    # 配置并启用 tmdb
    r = c.put(
        "/api/plugins/scraper/tmdb",
        json={"enabled": True, "config": {"api_key": "abc", "language": "en-US"}},
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    assert r.json()["config"]["api_key"] == "abc"

    # 写回磁盘且可被 load_config 读到
    reloaded = load_config(cfg_path)
    specs = {s.name: s for s in reloaded.plugin_specs("scraper")}
    assert "tmdb" in specs and specs["tmdb"].config["language"] == "en-US"

    # 刮削器固定为 TMDB、不可关闭：即便请求 enabled=false 也仍保持启用
    r = c.put("/api/plugins/scraper/tmdb", json={"enabled": False, "config": {"api_key": "abc"}})
    assert r.json()["enabled"] is True
    assert load_config(cfg_path).plugins["scraper"][0].enabled is True


def test_plugin_update_validation_error(client):
    c, _ = client
    # tmdb 必填 api_key，缺失 → 422
    r = c.put("/api/plugins/scraper/tmdb", json={"enabled": True, "config": {}})
    assert r.status_code == 422


def test_plugin_update_preserves_comments(client):
    c, tmp_path = client
    cfg_path = tmp_path / "config.yaml"
    # 追加注释
    original = cfg_path.read_text(encoding="utf-8")
    cfg_path.write_text("# 我的配置注释\n" + original, encoding="utf-8")

    c.put("/api/plugins/notifier/log", json={"enabled": True, "config": {}})
    assert "# 我的配置注释" in cfg_path.read_text(encoding="utf-8")


def test_update_unknown_plugin_404(client):
    c, _ = client
    r = c.put("/api/plugins/scraper/nope", json={"enabled": True, "config": {}})
    assert r.status_code == 404


def test_plugin_test_endpoint(client):
    c, _ = client
    # log 通知器：发测试通知，应 ok
    r = c.post("/api/plugins/notifier/log/test", json={"config": {}})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_plugin_test_validation_error(client):
    c, _ = client
    # tmdb 缺 api_key → 422
    r = c.post("/api/plugins/scraper/tmdb/test", json={"config": {}})
    assert r.status_code == 422


def test_settings_get(client):
    c, _ = client
    r = c.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert "library_dir" in body and "filters" in body and "naming" in body


def test_settings_update_and_reload(client):
    from mediamaid.config import load_config

    c, tmp_path = client
    cfg_path = tmp_path / "config.yaml"
    r = c.put(
        "/api/settings",
        json={
            "action": "copy",
            "filters": {"min_size_mb": 123},
            "naming": {"movie": "Films/{title}.{ext}"},
        },
    )
    assert r.status_code == 200
    assert r.json()["action"] == "copy"
    assert r.json()["filters"]["min_size_mb"] == 123

    reloaded = load_config(cfg_path)
    assert reloaded.action.value == "copy"
    assert reloaded.filters.min_size_mb == 123
    assert reloaded.naming.movie == "Films/{title}.{ext}"


def test_settings_validation_error(client):
    c, _ = client
    # action 非法 → 422
    r = c.put("/api/settings", json={"action": "teleport"})
    assert r.status_code == 422


def _make_feed(tmp_path):
    feed = tmp_path / "feed.xml"
    feed.write_text(
        '<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>'
        '<item><title>The.Matrix.1999.1080p</title><guid>m1</guid>'
        '<link>magnet:?xt=urn:btih:A</link></item>'
        '</channel></rss>',
        encoding="utf-8",
    )
    return feed


def test_tmdb_rules_crud(client):
    c, _ = client
    # 缺 tmdb_id → 422
    assert c.post("/api/tmdb-rules", json={"media_type": "episode"}).status_code == 422

    pat = r"\]\[(?P<title>[^\]]*遮天[^\]]*)\].*\[(?P<episode>\d+)\]"
    rid = c.post(
        "/api/tmdb-rules",
        json={
            "tmdb_id": 207468, "title": "遮天", "media_type": "episode",
            "category": "anime", "patterns": [pat], "season": 1,
            "ignore_episodes": [{"season": 1, "episodes": [13]}],
        },
    ).json()["id"]
    rules = c.get("/api/tmdb-rules").json()["rules"]
    assert any(r["id"] == rid and r["tmdb_id"] == 207468 for r in rules)

    assert c.put(f"/api/tmdb-rules/{rid}", json={"enabled": False}).status_code == 200
    assert c.get("/api/tmdb-rules").json()["rules"][0]["enabled"] is False
    assert c.delete(f"/api/tmdb-rules/{rid}").status_code == 200


def test_records_batch_delete_and_status(client):
    c, tmp_path = client
    from mediamaid.store import StateStore
    from pathlib import Path
    db = tmp_path / "s.db"
    with StateStore(db) as store:
        store.record(Path("/x/a.mkv"), Path("/lib/a.mkv"), "hardlink", "failed")
        store.record(Path("/x/b.mkv"), Path("/lib/b.mkv"), "hardlink", "skipped")
    ids = [r["id"] for r in c.get("/api/records").json()["records"]]
    assert len(ids) == 2

    # 批量改状态
    r = c.post("/api/records/status", json={"ids": ids, "status": "done"})
    assert r.status_code == 200 and r.json()["updated"] == 2
    assert all(x["status"] == "done" for x in c.get("/api/records").json()["records"])
    # 非法状态 → 422
    assert c.post("/api/records/status", json={"ids": ids, "status": "x"}).status_code == 422

    # 批量删除
    r = c.post("/api/records/delete", json={"ids": ids})
    assert r.status_code == 200 and r.json()["deleted"] == 2
    assert c.get("/api/records").json()["records"] == []


def test_parser_is_builtin(client):
    c, _ = client
    # guessit 在插件列表中恒为启用
    cats = {cat["category"]: cat for cat in c.get("/api/plugins").json()["categories"]}
    guessit = next(e for e in cats["parser"]["entries"] if e["name"] == "guessit")
    assert guessit["enabled"] is True
    # 请求停用也强制保持启用
    r = c.put("/api/plugins/parser/guessit", json={"enabled": False, "config": {}})
    assert r.status_code == 200 and r.json()["enabled"] is True


def test_subscribers_types_have_schema(client):
    c, _ = client
    r = c.get("/api/subscribers")
    assert r.status_code == 200
    rss = next(s for s in r.json()["subscribers"] if s["name"] == "rss")
    assert "url" in rss["schema"]["properties"]


def test_subscription_crud(client):
    c, tmp_path = client
    feed = _make_feed(tmp_path)

    # 校验失败：rss 缺 url → 422
    assert c.post(
        "/api/subscriptions", json={"name": "x", "subscriber": "rss", "config": {}}
    ).status_code == 422

    # 添加
    r = c.post(
        "/api/subscriptions",
        json={"name": "遮天", "subscriber": "rss", "config": {"url": f"file://{feed}"}},
    )
    assert r.status_code == 200
    sub_id = r.json()["id"]

    # 列表含该条
    lst = c.get("/api/subscriptions").json()["subscriptions"]
    assert any(s["id"] == sub_id and s["name"] == "遮天" for s in lst)

    # 删除
    assert c.delete(f"/api/subscriptions/{sub_id}").status_code == 200
    assert all(s["id"] != sub_id for s in c.get("/api/subscriptions").json()["subscriptions"])


def test_subscription_preview_and_download(client):
    c, tmp_path = client
    feed = _make_feed(tmp_path)
    c.put(
        "/api/plugins/downloader/dummy",
        json={"enabled": True, "config": {"save_path": str(tmp_path / "dl"), "size_mb": 1}},
    )
    sub_id = c.post(
        "/api/subscriptions",
        json={"name": "遮天", "subscriber": "rss", "config": {"url": f"file://{feed}"}},
    ).json()["id"]

    rels = c.get(f"/api/subscriptions/{sub_id}/preview").json()["releases"]
    rel = next(x for x in rels if x["title"] == "The.Matrix.1999.1080p")
    assert rel["seen"] is False

    r = c.post(
        "/api/releases/download",
        json={"title": rel["title"], "guid": rel["guid"], "magnet": rel["magnet"],
              "torrent_url": None, "link": None, "sub_id": sub_id},
    )
    assert r.status_code == 200
    assert (tmp_path / "dl" / "The.Matrix.1999.1080p.mkv").exists()

    # 该订阅的已处理历史出现该条
    done = c.get(f"/api/subscriptions/{sub_id}/releases").json()["releases"]
    assert any(x["guid"] == rel["guid"] for x in done)
