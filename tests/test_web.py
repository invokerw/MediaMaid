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


def test_dashboard(client):
    c, _ = client
    r = c.get("/")
    assert r.status_code == 200
    assert "仪表盘" in r.text


def test_plugins_page_lists_builtins(client):
    c, _ = client
    r = c.get("/plugins")
    assert r.status_code == 200
    assert "tmdb" in r.text
    assert "log" in r.text


def test_config_page(client):
    c, _ = client
    r = c.get("/config")
    assert r.status_code == 200
    assert "library_dir" in r.text


def test_scan_dry_run_then_real(client):
    c, tmp_path = client
    media = tmp_path / "media"

    # dry-run：不真正落地
    r = c.post("/api/scan", data={"dry_run": "true"})
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True
    assert body["summary"].get("done") == 1
    assert not media.exists()

    # 真实扫描：文件落地，记录出现
    r = c.post("/api/scan", data={"dry_run": "false"})
    assert r.json()["summary"].get("done") == 1
    assert (media / "Movies" / "The Matrix (1999)" / "The Matrix (1999).mkv").exists()

    r = c.get("/records")
    assert "The Matrix (1999).mkv" in r.text
