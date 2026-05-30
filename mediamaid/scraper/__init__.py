"""刮削元数据子包。"""

from .base import Scraper, NullScraper
from .tmdb import TMDBScraper

__all__ = ["Scraper", "NullScraper", "TMDBScraper"]
