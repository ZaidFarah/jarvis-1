from __future__ import annotations

import sys

from app.application import JarvisApplication
from config.settings import load_settings
from services.logging_service import configure_logging
from voice.audio_diagnostics import AudioDiagnostics, format_audio_check_report


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if "--audio-check" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        report = AudioDiagnostics(settings).run_full_check()
        print(format_audio_check_report(report))
        return 0 if report.is_successful else 1

    application = JarvisApplication()
    return application.run()


if __name__ == "__main__":
    sys.exit(main())
