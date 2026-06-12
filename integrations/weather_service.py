from __future__ import annotations

import json
import re
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from loguru import logger

from config.settings import AppSettings


_WEATHER_LOG_SINK_ID: int | None = None
_WEATHER_LOG_FILE: Path | None = None


WeatherRequester = Callable[[Request, float], Any]


@dataclass(frozen=True)
class WeatherQueryResult:
    success: bool
    text: str
    provider: str
    city: str
    request_attempted: bool
    api_key_detected: bool
    safe_error: str | None = None


@dataclass(frozen=True)
class WeatherCheckReport:
    enabled: bool
    provider: str
    api_key_detected: bool
    default_city: str
    units: str
    city: str
    request_attempted: bool
    success: bool
    text: str
    safe_error: str | None
    log_file: Path
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        if not self.enabled:
            return True
        if not self.api_key_detected:
            return True
        return self.success


class WeatherService:
    """Safe local weather integration with explicit configuration and fallback."""

    def __init__(
        self,
        settings: AppSettings,
        requester: WeatherRequester | None = None,
    ) -> None:
        self.settings = settings
        self.requester = requester or self._default_requester
        self.log_file = self.settings.log_dir / "weather.log"
        self.weather_logger = logger.bind(weather=True)
        self._ensure_weather_log_sink()

    def current_weather(self, city: str | None = None) -> WeatherQueryResult:
        target_city = self._normalize_city(city) or self.settings.weather_default_city
        provider = self.settings.weather_provider
        api_key_detected = self.settings.has_weather_api_key

        self.weather_logger.info(
            "Weather query enabled={} provider={} city={} units={} api_key_detected={}",
            self.settings.weather_enabled,
            provider,
            target_city,
            self.settings.weather_units,
            api_key_detected,
        )

        if not self.settings.weather_enabled:
            message = self._disabled_message(target_city)
            self.weather_logger.info("Weather fallback: disabled")
            return self._result(
                success=False,
                text=message,
                provider=provider,
                city=target_city,
                request_attempted=False,
                api_key_detected=api_key_detected,
                safe_error=message,
            )

        if not api_key_detected:
            message = "Weather is enabled, but WEATHER_API_KEY is not set."
            self.weather_logger.warning(message)
            return self._result(
                success=False,
                text=self._missing_key_message(target_city),
                provider=provider,
                city=target_city,
                request_attempted=False,
                api_key_detected=False,
                safe_error=message,
            )

        try:
            payload = self._request_current_weather(target_city)
            text = self._format_current_weather(payload, target_city)
            self.weather_logger.info("Weather request succeeded for city={}", target_city)
            return self._result(
                success=True,
                text=text,
                provider=provider,
                city=target_city,
                request_attempted=True,
                api_key_detected=True,
            )
        except Exception as exc:
            safe_error = format_weather_error(exc)
            self.weather_logger.error("Weather request failed: {}", safe_error)
            return self._result(
                success=False,
                text=self._service_unavailable_message(target_city),
                provider=provider,
                city=target_city,
                request_attempted=True,
                api_key_detected=True,
                safe_error=safe_error,
            )

    def run_check(self) -> WeatherCheckReport:
        target_city = self.settings.weather_default_city
        result = self.current_weather(target_city)
        errors = [result.safe_error] if result.safe_error else []
        return WeatherCheckReport(
            enabled=self.settings.weather_enabled,
            provider=self.settings.weather_provider,
            api_key_detected=result.api_key_detected,
            default_city=self.settings.weather_default_city,
            units=self.settings.weather_units,
            city=result.city,
            request_attempted=result.request_attempted,
            success=result.success,
            text=result.text,
            safe_error=result.safe_error,
            log_file=self.log_file,
            errors=errors,
        )

    def _request_current_weather(self, city: str) -> dict[str, Any]:
        query = urlencode(
            {
                "q": city,
                "appid": self.settings.weather_api_key,
                "units": self.settings.weather_units,
            }
        )
        url = f"https://api.openweathermap.org/data/2.5/weather?{query}"
        request = Request(url, headers={"User-Agent": "Jarvis/1.0"})

        with self._open(request, timeout=10.0) as response:
            payload = response.read()

        decoded = payload.decode("utf-8")
        data = json.loads(decoded)

        status_code = data.get("cod")
        if isinstance(status_code, str) and status_code.isdigit():
            status_code = int(status_code)
        if isinstance(status_code, int) and status_code != 200:
            message = data.get("message") or "Weather service returned an error."
            raise RuntimeError(f"OpenWeather response {status_code}: {message}")

        return data

    def _format_current_weather(self, payload: dict[str, Any], requested_city: str) -> str:
        city_name = str(payload.get("name") or requested_city)
        country = str((payload.get("sys") or {}).get("country") or "").strip()
        location = f"{city_name}, {country}" if country else city_name

        weather = payload.get("weather") or [{}]
        weather_description = str(weather[0].get("description") or "weather data unavailable").strip()
        main = payload.get("main") or {}
        wind = payload.get("wind") or {}

        temp = self._format_number(main.get("temp"))
        feels_like = self._format_number(main.get("feels_like"))
        humidity = self._format_integer(main.get("humidity"))
        wind_speed = self._format_number(wind.get("speed"))
        temp_unit, speed_unit = self._units_labels()

        parts = [f"Current weather in {location}: {weather_description}."]
        if temp is not None:
            parts.append(f"Temperature {temp}{temp_unit}.")
        if feels_like is not None:
            parts.append(f"Feels like {feels_like}{temp_unit}.")
        if humidity is not None:
            parts.append(f"Humidity {humidity}%.")
        if wind_speed is not None:
            parts.append(f"Wind {wind_speed} {speed_unit}.")
        return " ".join(parts)

    def _disabled_message(self, city: str) -> str:
        return (
            f"Weather is disabled. Enable WEATHER_ENABLED and set WEATHER_API_KEY to check "
            f"the current weather for {city}."
        )

    def _missing_key_message(self, city: str) -> str:
        return (
            f"Weather is enabled, but WEATHER_API_KEY is not set. "
            f"I cannot check the weather for {city} yet."
        )

    def _service_unavailable_message(self, city: str) -> str:
        return f"I couldn't fetch the weather for {city} right now. Please try again later."

    def _result(
        self,
        success: bool,
        text: str,
        provider: str,
        city: str,
        request_attempted: bool,
        api_key_detected: bool,
        safe_error: str | None = None,
    ) -> WeatherQueryResult:
        return WeatherQueryResult(
            success=success,
            text=text,
            provider=provider,
            city=city,
            request_attempted=request_attempted,
            api_key_detected=api_key_detected,
            safe_error=safe_error,
        )

    def _ensure_weather_log_sink(self) -> None:
        global _WEATHER_LOG_FILE, _WEATHER_LOG_SINK_ID
        if _WEATHER_LOG_SINK_ID is not None and _WEATHER_LOG_FILE == self.log_file:
            return

        if _WEATHER_LOG_SINK_ID is not None:
            try:
                logger.remove(_WEATHER_LOG_SINK_ID)
            except ValueError:
                pass

        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        _WEATHER_LOG_SINK_ID = logger.add(
            self.log_file,
            level="DEBUG",
            rotation="1 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
            filter=lambda record: bool(record["extra"].get("weather")),
        )
        _WEATHER_LOG_FILE = self.log_file

    @staticmethod
    def _default_requester(request: Request, timeout: float) -> Any:
        return urlopen(request, timeout=timeout)

    @contextmanager
    def _open(self, request: Request, timeout: float):
        response = self.requester(request, timeout)
        try:
            yield response
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    @staticmethod
    def _normalize_city(city: str | None) -> str:
        return " ".join((city or "").strip().split())

    def _units_labels(self) -> tuple[str, str]:
        if self.settings.weather_units == "imperial":
            return "F", "mph"
        if self.settings.weather_units == "standard":
            return "K", "m/s"
        return "C", "m/s"

    @staticmethod
    def _format_number(value: Any) -> str | None:
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if number.is_integer():
            return str(int(number))
        return f"{number:.1f}"

    @staticmethod
    def _format_integer(value: Any) -> str | None:
        if value is None:
            return None
        try:
            return str(int(float(value)))
        except (TypeError, ValueError):
            return None


def format_weather_error(error: Exception) -> str:
    error_type = type(error).__name__
    message = str(error).strip() or "No error details provided."
    return f"{error_type}: {_redact_secret_like_text(message)}"


def format_weather_check_report(report: WeatherCheckReport) -> str:
    lines = [
        "Jarvis Weather Check",
        "====================",
        f"Weather enabled: {_yes_no(report.enabled)}",
        f"Provider: {report.provider}",
        f"Default city: {report.default_city}",
        f"Units: {report.units}",
        f"API key detected: {_yes_no(report.api_key_detected)}",
        f"diagnostic log: {report.log_file}",
        f"request attempted: {_yes_no(report.request_attempted)}",
        f"request success: {_yes_no(report.success)}",
    ]

    if report.text:
        lines.extend(["", "Result:", f"  {report.text}"])

    if report.safe_error:
        lines.extend(["", "Error:", f"  {report.safe_error}"])

    return "\n".join(lines)


def _redact_secret_like_text(text: str) -> str:
    redacted = text
    redacted = re.sub(r"(appid=)[^&\s]+", r"\1[redacted]", redacted, flags=re.IGNORECASE)
    redacted = re.sub(r"\bsk-[A-Za-z0-9_\-]{10,}\b", "[redacted]", redacted)
    return redacted


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
