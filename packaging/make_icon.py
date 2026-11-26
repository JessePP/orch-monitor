"""Generuje packaging/orch_monitor.ico (QPixmap). Uruchom: python packaging/make_icon.py"""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from orch_monitor.ui.tray import default_icon  # noqa: E402

if __name__ == "__main__":
    app = QGuiApplication([])
    out = Path(__file__).with_name("orch_monitor.ico")
    pm = default_icon().pixmap(256, 256)
    if not pm.save(str(out), "ICO"):
        raise SystemExit("Zapis ICO nie powiodl sie")
    print(out)
