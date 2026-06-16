from __future__ import annotations

from pathlib import Path

from config.settings import AppSettings
from services import logging_service
from services.logging_service import add_managed_file_sink, configure_logging


def test_managed_file_sink_is_append_only_and_deduplicated(tmp_path: Path, monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_add(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return len(calls)

    logging_service._MANAGED_FILE_SINKS.clear()
    monkeypatch.setattr(logging_service.logger, "add", fake_add)

    log_file = tmp_path / "logs" / "voice_loop.log"
    first_sink = add_managed_file_sink(log_file, filter=lambda record: True)
    second_sink = add_managed_file_sink(log_file, filter=lambda record: True)

    assert first_sink == second_sink == 1
    assert log_file.parent.exists()
    assert len(calls) == 1
    assert calls[0]["args"][0] == log_file
    assert "rotation" not in calls[0]["kwargs"]
    assert "retention" not in calls[0]["kwargs"]
    assert calls[0]["kwargs"]["enqueue"] is True


def test_configure_logging_resets_managed_sinks(tmp_path: Path, monkeypatch) -> None:
    calls: list[Path] = []

    def fake_add(path, **kwargs):
        del kwargs
        calls.append(path)
        return len(calls)

    logging_service._MANAGED_FILE_SINKS[tmp_path / "old.log"] = 99
    monkeypatch.setattr(logging_service.logger, "remove", lambda: None)
    monkeypatch.setattr(logging_service.logger, "add", fake_add)

    settings = AppSettings(_env_file=None, log_dir=tmp_path / "logs")
    configure_logging(settings, console=False)

    assert calls == [tmp_path / "logs" / "jarvis.log"]
    assert len(logging_service._MANAGED_FILE_SINKS) == 1
