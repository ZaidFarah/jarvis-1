from __future__ import annotations

from pathlib import Path
from urllib.parse import quote_plus

from assistant.core import AssistantCore
from config.settings import AppSettings
from tools.browser_control import BrowserControl


class FakeOpenAIService:
    def chat(self, *args, **kwargs):  # pragma: no cover - defensive helper
        del args, kwargs
        raise AssertionError("OpenAI should not be called")


def test_browser_control_search_google_encodes_query(tmp_path: Path) -> None:
    captured: list[tuple[str, dict[str, object]]] = []

    def fake_open(url: str, **kwargs):
        captured.append((url, kwargs))
        return True

    settings = AppSettings(_env_file=None, log_dir=tmp_path)
    browser = BrowserControl(settings, browser_open=fake_open)

    result = browser.search_google("jarvis fast voice")

    assert result.opened is True
    assert captured
    assert captured[0][0] == f"https://www.google.com/search?q={quote_plus('jarvis fast voice')}"
    assert captured[0][1]["new"] == 0
    assert captured[0][1]["autoraise"] is True


def test_browser_control_search_youtube_encodes_query(tmp_path: Path) -> None:
    captured: list[tuple[str, dict[str, object]]] = []

    def fake_open(url: str, **kwargs):
        captured.append((url, kwargs))
        return True

    settings = AppSettings(_env_file=None, log_dir=tmp_path)
    browser = BrowserControl(settings, browser_open=fake_open)

    result = browser.search_youtube("red hud gui")

    assert result.opened is True
    assert captured
    assert captured[0][0] == f"https://www.youtube.com/results?search_query={quote_plus('red hud gui')}"


def test_browser_control_open_site_supports_chatgpt_and_calendar(tmp_path: Path) -> None:
    captured: list[tuple[str, dict[str, object]]] = []

    def fake_open(url: str, **kwargs):
        captured.append((url, kwargs))
        return True

    settings = AppSettings(_env_file=None, log_dir=tmp_path)
    browser = BrowserControl(settings, browser_open=fake_open)

    chatgpt_result = browser.open_site("chatgpt")
    calendar_result = browser.open_site("calendar")

    assert chatgpt_result.opened is True
    assert calendar_result.opened is True
    assert captured[0][0] == "https://chatgpt.com"
    assert captured[1][0] == "https://calendar.google.com"


def test_assistant_core_routes_browser_search_commands_locally(tmp_path: Path) -> None:
    captured: list[str] = []

    def fake_open(url: str, **kwargs):
        captured.append(url)
        return True

    settings = AppSettings(_env_file=None, log_dir=tmp_path)
    browser = BrowserControl(settings, browser_open=fake_open)
    assistant = AssistantCore(settings=settings, openai_service=FakeOpenAIService(), browser_control=browser)

    response = assistant.handle_command("search google for Jarvis browser control")

    assert response.accepted is True
    assert response.source == "browser"
    assert "Searched Google for Jarvis browser control." == response.text
    assert captured[0] == "https://www.google.com/search?q=Jarvis+browser+control"
