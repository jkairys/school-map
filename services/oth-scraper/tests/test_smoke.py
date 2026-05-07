from oth_scraper.api.app import app
from oth_scraper.config import settings


def test_health_route_registered():
    routes = [r.path for r in app.routes]
    assert "/health" in routes


def test_settings_defaults():
    assert settings.api_host in ("127.0.0.1", "0.0.0.0")
    assert settings.api_port == 8000
