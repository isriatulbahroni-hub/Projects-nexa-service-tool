"""Entry point for Nexa Service Tool.

Kept separate from app.py so the GUI module can also be imported (e.g. by
tests or tools/) without side effects like launching a QApplication.
"""
from app import QApplication, MainWindow, configure_logging, logger
import sys


def main() -> int:
    configure_logging()
    logger.info("Launching Nexa Service Tool via main.py")

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
