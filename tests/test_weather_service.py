from __future__ import annotations

import json
from pathlib import Path

import pytest

from config.settings import AppSettings
from integrations.weather_service import WeatherService, format_weather_check_report, format_weather_error


class FakeResponse:
    def __init__(self, body: dict) -> None:
        self._body = json.dumps(body).encode("utf-8")
        self.closed = False

    def read(self) -> bytes:
        return self._body

    def close(self) -> None:
        self.closed = True


def test_weather_disabled_does_not_attempt_request(tmp_path: Path) -> None:
    called = False

    def requester(request, timeout: float):
        nonlocal called
        del request, timeout
        called = True
        raise AssertionError("request should not be attempted")

    settings = AppSettings(_env_file=None, weather_enabled=False, weather_api_key="key-123", log_dir=tmp_path)
    service = WeatherService(settings, requester=requester)

    result = service.current_weather("London")

    assert called is False
    assert result.success is False
    assert "Weather is disabled" in result.text
    assert result.request_attempted is False


def test_weather_missing_api_key_does_not_attempt_request(tmp_path: Path) -> None:
    called = False

    def requester(request, timeout: float):
        nonlocal called
        del request, timeout
        called = True
        raise AssertionError("request should not be attempted")

    settings = AppSettings(_env_file=None, weather_enabled=True, weather_api_key="", log_dir=tmp_path)
    service = WeatherService(settings, requester=requester)

    result = service.current_weather("London")

    assert called is False
    assert result.success is False
    assert result.request_attempted is False
    assert "WEATHER_API_KEY is not set" in (result.safe_error or "")


def test_weather_provider_configuration_and_success(tmp_path: Path) -> None:
    captured: dict[str, str] = {}

    def requester(request, timeout: float):
        captured["url"] = request.full_url
        captured["timeout"] = str(timeout)
        return FakeResponse(
            {
                "name": "London",
                "sys": {"country": "GB"},
                "weather": [{"description": "clear sky"}],
                "main": {"temp": 12.5, "feels_like": 11.8, "humidity": 71},
                "wind": {"speed": 4.2},
                "cod": 200,
            }
        )

    settings = AppSettings(
        _env_file=None,
        weather_enabled=True,
        weather_api_key="key-123",
        weather_default_city="Nottingham",
        weather_units="metric",
        log_dir=tmp_path,
    )
    report = WeatherService(settings, requester=requester).run_check()
    text = format_weather_check_report(report)

    assert report.enabled is True
    assert report.api_key_detected is True
    assert report.request_attempted is True
    assert report.success is True
    assert "q=Nottingham" in captured["url"]
    assert "units=metric" in captured["url"]
    assert "API key detected: yes" in text
    assert "key-123" not in text


def test_weather_safe_error_formatting_redacts_key_like_text() -> None:
    error = RuntimeError("request failed with key sk-test-secret and appid=secret123")

    text = format_weather_error(error)

    assert "RuntimeError:" in text
    assert "sk-test-secret" not in text
    assert "appid=secret123" not in text
    assert "[redacted]" in text


def test_weather_check_report_redacts_api_key_from_output(tmp_path: Path) -> None:
    def requester(request, timeout: float):
        del request, timeout
        raise RuntimeError("failed with appid=key-123")

    settings = AppSettings(_env_file=None, weather_enabled=True, weather_api_key="key-123", log_dir=tmp_path)
    report = WeatherService(settings, requester=requester).run_check()
    text = format_weather_check_report(report)

    assert report.success is False
    assert report.safe_error is not None
    assert "key-123" not in report.safe_error
    assert "key-123" not in text

