from __future__ import annotations

import sys

from app.application import JarvisApplication


def main() -> int:
    application = JarvisApplication()
    return application.run()


if __name__ == "__main__":
    sys.exit(main())
