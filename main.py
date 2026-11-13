"""Run EazyFix AI Video Studio."""

import sys

from PySide6.QtWidgets import QApplication

from eazyfix_studio import __version__
from eazyfix_studio.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("EazyFix AI Video Studio")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("EazyFix")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
