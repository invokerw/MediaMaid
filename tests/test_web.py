from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from mediamaid.web import create_app

BIG = b"0" * (60 * 1024 * 1024)


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
    app = create_app(cfg_path)
    return TestClient(app), tmp_path


def test_dashboard_api(client):
    c, _ = client
    r = c.get("/api/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert "counts" in body and "records" in body


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
