"""MediaMaid Web UI（FastAPI + Jinja2，需 pip install 'mediamaid[web]'）。"""

from .app import create_app

__all__ = ["create_app"]
